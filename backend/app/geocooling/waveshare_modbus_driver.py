"""Pilote direct du relais Ethernet Waveshare via Modbus TCP.

Le pilote reste désarmé par défaut. Les commandes OFF sont toujours permises,
mais toute commande ON exige GEOCOOLING_HARDWARE_ARMED=true.
"""

from __future__ import annotations

import logging
import os
import socket
import struct
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("sbc.geocooling.waveshare")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "true" if default else "false")
    return value.strip().lower() in {"1", "true", "yes", "on"}


class ModbusTCPError(RuntimeError):
    """Erreur de transport ou de protocole Modbus TCP."""


class ModbusTCPClient:
    """Client Modbus TCP minimal pour lecture/écriture de bobines."""

    def __init__(self, host: str, port: int, unit_id: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._transaction_id = 0
        self._lock = threading.RLock()

    def _next_transaction_id(self) -> int:
        self._transaction_id = (self._transaction_id + 1) & 0xFFFF
        return self._transaction_id

    @staticmethod
    def _recv_exact(sock: socket.socket, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = sock.recv(remaining)
            if not chunk:
                raise ModbusTCPError("Connexion Modbus fermée prématurément.")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _request(self, function_code: int, payload: bytes) -> bytes:
        with self._lock:
            transaction_id = self._next_transaction_id()
            pdu = bytes([function_code]) + payload
            header = struct.pack(">HHHB", transaction_id, 0, len(pdu) + 1, self.unit_id)

            try:
                with socket.create_connection(
                    (self.host, self.port), timeout=self.timeout
                ) as sock:
                    sock.settimeout(self.timeout)
                    sock.sendall(header + pdu)
                    response_header = self._recv_exact(sock, 7)
                    rx_transaction, protocol_id, length, unit_id = struct.unpack(
                        ">HHHB", response_header
                    )
                    if protocol_id != 0:
                        raise ModbusTCPError("Identifiant de protocole Modbus invalide.")
                    if rx_transaction != transaction_id:
                        raise ModbusTCPError("Transaction Modbus incohérente.")
                    if unit_id != self.unit_id:
                        raise ModbusTCPError("Unit ID Modbus incohérent.")
                    response_pdu = self._recv_exact(sock, length - 1)
            except (OSError, TimeoutError) as exc:
                raise ModbusTCPError(
                    f"Waveshare inaccessible sur {self.host}:{self.port}: {exc}"
                ) from exc

            if not response_pdu:
                raise ModbusTCPError("Réponse Modbus vide.")
            response_function = response_pdu[0]
            if response_function == (function_code | 0x80):
                exception_code = response_pdu[1] if len(response_pdu) > 1 else -1
                raise ModbusTCPError(
                    f"Exception Modbus fonction 0x{function_code:02X}, code {exception_code}."
                )
            if response_function != function_code:
                raise ModbusTCPError("Fonction Modbus de réponse inattendue.")
            return response_pdu[1:]

    def read_coil(self, address: int) -> bool:
        response = self._request(0x01, struct.pack(">HH", address, 1))
        if len(response) < 2 or response[0] < 1:
            raise ModbusTCPError("Réponse de lecture de bobine invalide.")
        return bool(response[1] & 0x01)

    def write_coil(self, address: int, enabled: bool) -> None:
        value = 0xFF00 if enabled else 0x0000
        expected = struct.pack(">HH", address, value)
        response = self._request(0x05, expected)
        if response != expected:
            raise ModbusTCPError("Confirmation d'écriture de bobine invalide.")


class WaveshareModbusDriver:
    """Pilote des relais vanne et circulateur du module Waveshare."""

    def __init__(self, client: ModbusTCPClient | None = None) -> None:
        self.host = os.getenv("GEOCOOLING_WAVESHARE_HOST", "192.168.10.200").strip()
        self.port = int(os.getenv("GEOCOOLING_WAVESHARE_PORT", "502"))
        self.unit_id = int(os.getenv("GEOCOOLING_WAVESHARE_UNIT_ID", "1"))
        self.timeout = max(0.2, float(os.getenv("GEOCOOLING_WAVESHARE_TIMEOUT_SECONDS", "2")))
        self.address_base = int(os.getenv("GEOCOOLING_WAVESHARE_ADDRESS_BASE", "0"))
        self.valve_relay = int(os.getenv("GEOCOOLING_WAVESHARE_VALVE_RELAY", "1"))
        self.pump_relay = int(os.getenv("GEOCOOLING_WAVESHARE_PUMP_RELAY", "2"))
        self.armed = env_bool("GEOCOOLING_HARDWARE_ARMED", False)
        self.verify_writes = env_bool("GEOCOOLING_WAVESHARE_VERIFY_WRITES", True)

        if not 1 <= self.valve_relay <= 8 or not 1 <= self.pump_relay <= 8:
            raise RuntimeError("Les relais Waveshare doivent être compris entre 1 et 8.")
        if self.valve_relay == self.pump_relay:
            raise RuntimeError("La vanne et la pompe ne peuvent pas utiliser le même relais.")

        self.valve_address = self.address_base + self.valve_relay - 1
        self.pump_address = self.address_base + self.pump_relay - 1
        self.client = client or ModbusTCPClient(
            self.host, self.port, self.unit_id, self.timeout
        )
        self._lock = threading.RLock()
        self._valve_open = False
        self._pump_running = False
        self._connected = False
        self._last_connected_at: str | None = None
        self._last_action_at: str | None = None
        self._last_error: str | None = None

    def set_armed(self, armed: bool) -> bool:
        """Arme ou désarme le pilote à chaud.

        Le désarmement force d'abord l'arrêt des sorties afin qu'aucun
        relais ne reste actif après la perte d'autorisation.
        """
        requested = bool(armed)
        with self._lock:
            if not requested:
                self.force_safe_state()
            self.armed = requested
            self._last_action_at = utc_iso()
            logger.warning(
                "Waveshare matériel %s",
                "ARMÉ" if requested else "DÉSARMÉ",
            )
            return self.armed

    def _require_armed(self, action: str) -> None:
        if not self.armed:
            raise RuntimeError(
                f"Commande {action} refusée : matériel désarmé. "
                "Configurer GEOCOOLING_HARDWARE_ARMED=true après vérification du câblage."
            )

    def _read_outputs(self) -> tuple[bool, bool]:
        valve = self.client.read_coil(self.valve_address)
        pump = self.client.read_coil(self.pump_address)
        with self._lock:
            self._connected = True
            self._last_connected_at = utc_iso()
            self._last_error = None
            self._valve_open = valve
            self._pump_running = pump
        return valve, pump

    def _write(self, address: int, enabled: bool, label: str) -> None:
        try:
            self.client.write_coil(address, enabled)
            if self.verify_writes and self.client.read_coil(address) != enabled:
                raise ModbusTCPError(f"Le retour du relais {label} ne confirme pas la commande.")
            with self._lock:
                self._connected = True
                self._last_connected_at = utc_iso()
                self._last_action_at = utc_iso()
                self._last_error = None
                if address == self.valve_address:
                    self._valve_open = enabled
                elif address == self.pump_address:
                    self._pump_running = enabled
            logger.info("Waveshare relais %s -> %s", label, "ON" if enabled else "OFF")
        except Exception as exc:
            with self._lock:
                self._connected = False
                self._last_error = str(exc)
            raise

    def open_valve(self) -> None:
        self._require_armed("OPEN_VALVE")
        self._write(self.valve_address, True, "vanne")

    def close_valve(self) -> None:
        self._write(self.valve_address, False, "vanne")

    def start_pump(self) -> None:
        self._require_armed("START_PUMP")
        valve, _ = self._read_outputs()
        if not valve:
            raise RuntimeError("Démarrage circulateur refusé : le relais de vanne est OFF.")
        self._write(self.pump_address, True, "pompe")

    def stop_pump(self) -> None:
        self._write(self.pump_address, False, "pompe")

    def force_safe_state(self) -> None:
        errors: list[str] = []
        try:
            self.stop_pump()
        except Exception as exc:
            errors.append(f"pompe: {exc}")
        try:
            self.close_valve()
        except Exception as exc:
            errors.append(f"vanne: {exc}")
        if errors:
            raise RuntimeError("État sécurisé incomplet : " + " ; ".join(errors))

    def status(self) -> dict[str, Any]:
        try:
            valve, pump = self._read_outputs()
        except Exception as exc:
            with self._lock:
                self._connected = False
                self._last_error = str(exc)
                valve = self._valve_open
                pump = self._pump_running

        with self._lock:
            return {
                "driver": "waveshare_modbus",
                "simulation": False,
                "connected": self._connected,
                "device_online": self._connected,
                "ready": self._connected and self.armed,
                "armed": self.armed,
                "valve_open": valve,
                "pump_running": pump,
                "last_connected_at": self._last_connected_at,
                "last_heartbeat_at": self._last_connected_at,
                "last_action_at": self._last_action_at,
                "last_error": self._last_error,
                "device": {
                    "host": self.host,
                    "port": self.port,
                    "unit_id": self.unit_id,
                    "address_base": self.address_base,
                    "valve_relay": self.valve_relay,
                    "pump_relay": self.pump_relay,
                    "verify_writes": self.verify_writes,
                },
            }
