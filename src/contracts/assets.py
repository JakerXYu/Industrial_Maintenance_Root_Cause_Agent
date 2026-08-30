"""Asset contracts."""

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class AssetType(str, Enum):
    HYDRAULIC_PRESS = "hydraulic_press"
    ROBOTIC_WELDING_CELL = "robotic_welding_cell"
    CNC_MACHINE = "cnc_machine"
    INDUSTRIAL_PUMP = "industrial_pump"


class AssetCriticality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AssetStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNDER_MAINTENANCE = "under_maintenance"
    RETIRED = "retired"


class Asset(BaseModel):
    asset_id: str = Field(min_length=1)
    asset_name: str = Field(min_length=1)
    asset_type: AssetType
    line: str
    department: str
    manufacturer: str
    model: str
    install_date: date
    criticality: AssetCriticality
    status: AssetStatus = AssetStatus.ACTIVE
