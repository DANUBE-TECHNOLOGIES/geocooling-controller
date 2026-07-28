"""Pilote direct du relais Ethernet Waveshare via Modbus TCP.

PATCH C018 — couche matérielle uniquement.

Le pilote reste désarmé par défaut. Les commandes OFF sont toujours permises,
mais toute commande ON exige ``GEOCOOLING_HARDWARE_ARMED=true`` ou un armement
explicite par l'API manuelle. Aucune décision du Brain n'est reliée à ce pilote
par ce patch.
"""

from __future__ import annotations

import logging
import os
import socket
import struct
import threading
import time
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
    """Client Modbus TCP minimal et thread-safe pour les bobines.

    Une connexion courte est volontairement utilisée pour chaque requête : le
    module Waveshare accepte ce fonctionnement et une rupture de session ne
    laisse ainsi aucun socket périmé dans le processus. Les tentatives de
    reconnexion sont prises en charge par ``retries``.
    """

    def __init__(
        self,
        host: str,
        port: int,
        unit_id: int,
        timeout: float,
        retries: int = 1,
        retry_delay: float = 0.15,
    ) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.retries = max(0, int(retries))
        self.retry_delay = max(0.0, float(retry_delay))
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

    def _request_once(self, function_code: int, payload: bytes) -> bytes:
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
                if length < 2 or length > 254:
                    raise ModbusTCPError("Longueur de réponse Modbus invalide.")
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

    def _request(self, function_code: int, payload: bytes) -> bytes:
        with self._lock:
            last_error: Exception | None = None
            for attempt in range(self.retries + 1):
                try:
                    return self._request_once(function_code, payload)
                except ModbusTCPError as exc:
                    last_error = exc
                    if attempt >= self.retries:
                        break
                    if self.retry_delay:
                        time.sleep(self.retry_delay)
            assert last_error is not None
            raise last_error

    def read_coils(self, address: int, quantity: int) -> list[bool]:
        if address < 0:
            raise ValueError("L'adresse Modbus doit être positive.")
        if not 1 <= quantity <= 2000:
            raise ValueError("La quantité de bobines doit être comprise entre 1 et 2000.")
        response = self._request(0x01, struct.pack(">HH", address, quantity))
        expected_bytes = (quantity + 7) // 8
        if len(response) != expected_bytes + 1 or response[0] != expected_bytes:
            raise ModbusTCPError("Réponse de lecture des bobines invalide.")
        data = response[1:]
        return [bool(data[index // 8] & (1 << (index % 8))) for index in range(quantity)]

    def read_coil(self, address: int) -> bool:
        return self.read_coils(address, 1)[0]

    def write_coil(self, address: int, enabled: bool) -> None:
        if address < 0:
            raise ValueError("L'adresse Modbus doit être positive.")
        value = 0xFF00 if enabled else 0x0000
        expected = struct.pack(">HH", address, value)
        response = self._request(0x05, expected)
        if response != expected:
            raise ModbusTCPError("Confirmation d'écriture de bobine invalide.")

    def write_coils(self, address: int, values: list[bool]) -> None:
        if address < 0:
            raise ValueError("L'adresse Modbus doit être positive.")
        if not values or len(values) > 1968:
            raise ValueError("Le nombre de bobines doit être compris entre 1 et 1968.")
        byte_count = (len(values) + 7) // 8
        packed = bytearray(byte_count)
        for index, enabled in enumerate(values):
            if enabled:
                packed[index // 8] |= 1 << (index % 8)
        payload = struct.pack(">HHB", address, len(values), byte_count) + bytes(packed)
        expected = struct.pack(">HH", address, len(values))
        response = self._request(0x0F, payload)
        if response != expected:
            raise ModbusTCPError("Confirmation d'écriture multiple invalide.")


class WaveshareModbusDriver:
    """Pilote sécurisé des huit relais du module Waveshare."""

    RELAY_COUNT = 8

    def __init__(self, client: ModbusTCPClient | None = None) -> None:
        self.host = os.getenv("GEOCOOLING_WAVESHARE_HOST", "192.168.10.122").strip()
        self.port = int(os.getenv("GEOCOOLING_WAVESHARE_PORT", "502"))
        self.unit_id = int(os.getenv("GEOCOOLING_WAVESHARE_UNIT_ID", "1"))
        self.timeout = max(0.2, float(os.getenv("GEOCOOLING_WAVESHARE_TIMEOUT_SECONDS", "2")))
        self.retries = max(0, int(os.getenv("GEOCOOLING_WAVESHARE_RETRIES", "1")))
        self.retry_delay = max(0.0, float(os.getenv("GEOCOOLING_WAVESHARE_RETRY_DELAY_SECONDS", "0.15")))
        self.address_base = int(os.getenv("GEOCOOLING_WAVESHARE_ADDRESS_BASE", "0"))
        self.valve_relay = int(os.getenv("GEOCOOLING_WAVESHARE_VALVE_RELAY", "1"))
        self.pump_relay = int(os.getenv("GEOCOOLING_WAVESHARE_PUMP_RELAY", "2"))
        self.armed = env_bool("GEOCOOLING_HARDWARE_ARMED", False)
        self.verify_writes = env_bool("GEOCOOLING_WAVESHARE_VERIFY_WRITES", True)

        if not 1 <= self.valve_relay <= self.RELAY_COUNT or not 1 <= self.pump_relay <= self.RELAY_COUNT:
            raise RuntimeError("Les relais Waveshare doivent être compris entre 1 et 8.")
        if self.valve_relay == self.pump_relay:
            raise RuntimeError("La vanne et la pompe ne peuvent pas utiliser le même relais.")

        self.valve_address = self._relay_address(self.valve_relay)
        self.pump_address = self._relay_address(self.pump_relay)
        self.client = client or ModbusTCPClient(
            self.host,
            self.port,
            self.unit_id,
            self.timeout,
            retries=self.retries,
            retry_delay=self.retry_delay,
        )
        self._lock = threading.RLock()
        self._relay_states = [False] * self.RELAY_COUNT
        self._connected = False
        self._last_connected_at: str | None = None
        self._last_action_at: str | None = None
        self._last_error: str | None = None
        self._successful_requests = 0
        self._failed_requests = 0

    def _relay_address(self, relay_id: int) -> int:
        if not 1 <= int(relay_id) <= self.RELAY_COUNT:
            raise ValueError("Le numéro de relais doit être compris entre 1 et 8.")
        return self.address_base + int(relay_id) - 1

    def set_armed(self, armed: bool) -> bool:
        requested = bool(armed)
        with self._lock:
            if not requested:
                self.force_safe_state()
            self.armed = requested
            self._last_action_at = utc_iso()
            logger.warning("Waveshare matériel %s", "ARMÉ" if requested else "DÉSARMÉ")
            return self.armed

    def _require_armed(self, action: str) -> None:
        if not self.armed:
            raise RuntimeError(
                f"Commande {action} refusée : matériel désarmé. "
                "Configurer GEOCOOLING_HARDWARE_ARMED=true après vérification du câblage."
            )

    def _record_success(self, states: list[bool] | None = None) -> None:
        with self._lock:
            self._connected = True
            self._last_connected_at = utc_iso()
            self._last_error = None
            self._successful_requests += 1
            if states is not None:
                self._relay_states = list(states)

    def _record_failure(self, exc: Exception) -> None:
        with self._lock:
            self._connected = False
            self._last_error = str(exc)
            self._failed_requests += 1

    def read_relays(self) -> list[bool]:
        try:
            states = self.client.read_coils(self.address_base, self.RELAY_COUNT)
            self._record_success(states)
            return states
        except AttributeError:
            # Compatibilité avec les petits clients factices historiques des tests.
            states = [self.client.read_coil(self._relay_address(i)) for i in range(1, 9)]
            self._record_success(states)
            return states
        except Exception as exc:
            self._record_failure(exc)
            raise

    def read_relay(self, relay_id: int) -> bool:
        address = self._relay_address(relay_id)
        try:
            state = self.client.read_coil(address)
            with self._lock:
                self._relay_states[relay_id - 1] = state
            self._record_success()
            return state
        except Exception as exc:
            self._record_failure(exc)
            raise

    def _write_relay(self, relay_id: int, enabled: bool, label: str | None = None) -> None:
        if enabled:
            self._require_armed(f"RELAY_{relay_id}_ON")
        address = self._relay_address(relay_id)
        try:
            self.client.write_coil(address, enabled)
            if self.verify_writes and self.client.read_coil(address) != enabled:
                raise ModbusTCPError(f"Le retour du relais {relay_id} ne confirme pas la commande.")
            with self._lock:
                self._relay_states[relay_id - 1] = enabled
                self._last_action_at = utc_iso()
            self._record_success()
            logger.info("Waveshare relais %s -> %s", label or relay_id, "ON" if enabled else "OFF")
        except Exception as exc:
            self._record_failure(exc)
            raise

    def set_relay(self, relay_id: int, enabled: bool) -> None:
        self._write_relay(relay_id, bool(enabled))

    def open_valve(self) -> None:
        self._write_relay(self.valve_relay, True, "vanne")

    def close_valve(self) -> None:
        self._write_relay(self.valve_relay, False, "vanne")

    def start_pump(self) -> None:
        self._require_armed("START_PUMP")
        if not self.read_relay(self.valve_relay):
            raise RuntimeError("Démarrage circulateur refusé : le relais de vanne est OFF.")
        self._write_relay(self.pump_relay, True, "pompe")

    def stop_pump(self) -> None:
        self._write_relay(self.pump_relay, False, "pompe")

    def all_off(self) -> None:
        """Coupe les huit sorties, y compris celles non affectées."""
        try:
            if hasattr(self.client, "write_coils"):
                self.client.write_coils(self.address_base, [False] * self.RELAY_COUNT)
                if self.verify_writes and any(self.read_relays()):
                    raise ModbusTCPError("Le retour matériel indique encore un relais actif.")
                with self._lock:
                    self._relay_states = [False] * self.RELAY_COUNT
                    self._last_action_at = utc_iso()
                self._record_success()
                return
        except Exception as exc:
            self._record_failure(exc)
            raise

        # Repli pour les clients factices et matériels ne supportant pas 0x0F.
        errors: list[str] = []
        for relay_id in range(1, self.RELAY_COUNT + 1):
            try:
                self._write_relay(relay_id, False)
            except Exception as exc:  # pragma: no cover - agrégation de défauts
                errors.append(f"relais {relay_id}: {exc}")
        if errors:
            raise RuntimeError("Arrêt global incomplet : " + " ; ".join(errors))

    def force_safe_state(self) -> None:
        """État sûr hydraulique : pompe OFF puis vanne OFF."""
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
            states = self.read_relays()
        except Exception:
            with self._lock:
                states = list(self._relay_states)

        valve = states[self.valve_relay - 1]
        pump = states[self.pump_relay - 1]
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
                "relays": [
                    {"relay": index + 1, "address": self._relay_address(index + 1), "on": state}
                    for index, state in enumerate(states)
                ],
                "last_connected_at": self._last_connected_at,
                "last_heartbeat_at": self._last_connected_at,
                "last_action_at": self._last_action_at,
                "last_error": self._last_error,
                "metrics": {
                    "successful_requests": self._successful_requests,
                    "failed_requests": self._failed_requests,
                },
                "device": {
                    "host": self.host,
                    "port": self.port,
                    "unit_id": self.unit_id,
                    "relay_count": self.RELAY_COUNT,
                    "address_base": self.address_base,
                    "valve_relay": self.valve_relay,
                    "pump_relay": self.pump_relay,
                    "verify_writes": self.verify_writes,
                    "timeout_seconds": self.timeout,
                    "retries": self.retries,
                    "retry_delay_seconds": self.retry_delay,
                },
            }
