"""
Weather Intelligence GeoCooling.

Ce module est strictement en lecture seule :
- aucune commande MQTT ;
- aucune commande Modbus ;
- aucune écriture sur les relais ;
- aucune modification directe de décision du Brain.
"""

from app.geocooling.weather.service import WeatherService

__all__ = ["WeatherService"]
