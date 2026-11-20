"""Sensors for loans (due dates) and reservations ready for pickup."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HelmetConfigEntry, HelmetCoordinator
from .api import HelmetData
from .const import BASE_URL, DOMAIN


@dataclass(frozen=True, kw_only=True)
class HelmetSensorDescription(SensorEntityDescription):
    value: Callable[[HelmetData], Any]
    attributes: Callable[[HelmetData], dict[str, Any]] | None = None


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _loan_list(data: HelmetData) -> dict[str, Any]:
    return {
        "loans": [
            {"title": loan.title, "due_date": _iso(loan.due_date)}
            for loan in data.loans
        ]
    }


def _ready_list(data: HelmetData) -> dict[str, Any]:
    return {
        "holds": [
            {"title": hold.title, "pickup_by": _iso(hold.pickup_by)}
            for hold in data.holds
            if hold.ready
        ],
        "waiting": len([hold for hold in data.holds if not hold.ready]),
    }


def _hold_list(data: HelmetData) -> dict[str, Any]:
    return {
        "holds": [
            {
                "title": hold.title,
                "ready": hold.ready,
                "pickup_by": _iso(hold.pickup_by),
                "queue_position": hold.queue_position,
                "queue_length": hold.queue_length,
            }
            for hold in data.holds
        ]
    }


SENSORS = (
    HelmetSensorDescription(
        key="loans",
        translation_key="loans",
        icon="mdi:book-multiple",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.loans_total,
        attributes=_loan_list,
    ),
    HelmetSensorDescription(
        key="next_due",
        translation_key="next_due",
        device_class=SensorDeviceClass.DATE,
        value=lambda data: next(
            (loan.due_date for loan in data.loans if loan.due_date), None
        ),
    ),
    HelmetSensorDescription(
        key="overdue",
        translation_key="overdue",
        icon="mdi:book-alert",
        value=lambda data: data.loans_overdue,
    ),
    HelmetSensorDescription(
        key="reservations",
        translation_key="reservations",
        icon="mdi:book-clock",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: len(data.holds),
        attributes=_hold_list,
    ),
    HelmetSensorDescription(
        key="ready_for_pickup",
        translation_key="ready_for_pickup",
        icon="mdi:bookshelf",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.holds_ready,
        attributes=_ready_list,
    ),
    HelmetSensorDescription(
        key="next_pickup_deadline",
        translation_key="next_pickup_deadline",
        device_class=SensorDeviceClass.DATE,
        value=lambda data: next(
            (hold.pickup_by for hold in data.holds if hold.pickup_by), None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HelmetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(HelmetSensor(coordinator, entry, desc) for desc in SENSORS)


class HelmetSensor(CoordinatorEntity[HelmetCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: HelmetSensorDescription

    def __init__(
        self,
        coordinator: HelmetCoordinator,
        entry: HelmetConfigEntry,
        description: HelmetSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer="Helmet",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"{BASE_URL}/MyResearch/CheckedOut",
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attributes = self.entity_description.attributes
        return attributes(self.coordinator.data) if attributes else None
