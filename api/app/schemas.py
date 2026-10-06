"""Request/response models, organised by persona category.

Literal types and ranges reject invalid values with a clear 422 response.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Gender = Literal["Female", "Male"]
Internet = Literal["Fiber Optic", "Cable", "DSL", "None"]
Contract = Literal["Month-to-Month", "One Year", "Two Year"]
Payment = Literal["Bank Withdrawal", "Credit Card", "Mailed Check"]
Offer = Literal["None", "Offer A", "Offer B", "Offer C", "Offer D", "Offer E"]
Lifestyle = Literal["Family", "Streamer", "Gamer", "Remote worker", "Budget", "Senior", "Homeowner", "Student"]
Channel = Literal["Email", "Phone", "SMS", "In-app"]

LIFESTYLES = list(Lifestyle.__args__)
CHANNELS = list(Channel.__args__)


class Contact(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str | None = Field(None, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = Field(None, max_length=30)


class Geographic(BaseModel):
    city: str | None = Field(None, max_length=60)
    zip_code: str | None = Field(None, max_length=10)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    population: int | None = Field(None, ge=0, le=10_000_000, description="people in the zip code area")


class Demographic(BaseModel):
    gender: Gender = "Female"
    age: int = Field(40, ge=18, le=100)
    married: bool = False
    num_dependents: int = Field(0, ge=0, le=10)


class Technographic(BaseModel):
    phone_service: bool = True
    multiple_lines: bool = False
    internet_type: Internet = "Fiber Optic"
    avg_monthly_gb: int = Field(20, ge=0, le=500)
    unlimited_data: bool = False
    online_security: bool = False
    online_backup: bool = False
    device_protection: bool = False
    premium_tech_support: bool = False
    streaming_tv: bool = False
    streaming_movies: bool = False
    streaming_music: bool = False


class Behavioural(BaseModel):
    tenure_months: int = Field(12, ge=0, le=120)
    contract: Contract = "Month-to-Month"
    payment_method: Payment = "Bank Withdrawal"
    paperless_billing: bool = True
    offer: Offer = "None"
    referrals: int = Field(0, ge=0, le=20)
    monthly_charge: float = Field(70.0, gt=0, le=500)
    avg_long_distance: float = Field(0.0, ge=0, le=200, description="average monthly long-distance charge")
    total_charges: float | None = Field(None, ge=0, description="defaults to tenure x monthly charge")
    total_refunds: float = Field(0.0, ge=0)
    total_extra_data_charges: float = Field(0.0, ge=0)


class Psychographic(BaseModel):
    satisfaction_score: int | None = Field(None, ge=1, le=5,
                                           description="survey answer 1-5; switches to the survey model")
    # Not model inputs (no labelled data exists) - used by the action center.
    price_sensitivity: int | None = Field(None, ge=1, le=5)
    brand_loyalty: int | None = Field(None, ge=1, le=5)
    preferred_channel: Channel | None = None
    lifestyle: Lifestyle | None = None
    interests: list[str] = Field(default_factory=list, max_length=10)


class CustomerIn(BaseModel):
    contact: Contact
    geographic: Geographic = Geographic()
    demographic: Demographic = Demographic()
    technographic: Technographic = Technographic()
    behavioural: Behavioural = Behavioural()
    psychographic: Psychographic = Psychographic()

    def to_profile(self, city_lookup: dict[str, dict] | None = None) -> dict:
        """The flat model profile. Missing location details come from the city."""
        geo = self.geographic.model_dump()
        known = (city_lookup or {}).get((geo.get("city") or "").strip().lower())
        default = (city_lookup or {}).get("los angeles", {})
        for key in ("latitude", "longitude", "population", "zip_code"):
            if geo.get(key) in (None, ""):
                geo[key] = (known or default).get(key)
        tech = self.technographic.model_dump()
        if tech["internet_type"] == "None":
            for key in ("online_security", "online_backup", "device_protection", "premium_tech_support",
                        "streaming_tv", "streaming_movies", "streaming_music", "unlimited_data"):
                tech[key] = False
            tech["avg_monthly_gb"] = 0
        if not tech["phone_service"]:
            tech["multiple_lines"] = False
        beh = self.behavioural.model_dump()
        if beh["total_charges"] is None:
            beh["total_charges"] = round(beh["tenure_months"] * beh["monthly_charge"], 2)
        beh["total_long_distance_charges"] = round(beh["tenure_months"] * beh["avg_long_distance"], 2)
        return {**geo, **self.demographic.model_dump(), **tech, **beh,
                "satisfaction_score": self.psychographic.satisfaction_score}

    def persona(self) -> dict:
        return self.psychographic.model_dump(exclude={"satisfaction_score"})

    # ---------------------------------------------------------- flat CSV rows
    @classmethod
    def flat_fields(cls) -> list[str]:
        fields = []
        for section in ("contact", "geographic", "demographic", "technographic", "behavioural", "psychographic"):
            fields += [f for f in cls.model_fields[section].annotation.model_fields if f != "interests"]
        return fields

    @classmethod
    def from_flat(cls, row: dict[str, Any]) -> CustomerIn:
        clean = {k: (None if (v is None or str(v).strip() == "") else str(v).strip()) for k, v in row.items()}
        nested: dict[str, dict] = {}
        for section in ("contact", "geographic", "demographic", "technographic", "behavioural", "psychographic"):
            model = cls.model_fields[section].annotation
            values = {k: clean[k] for k in model.model_fields if clean.get(k) is not None}
            nested[section] = values
        return cls.model_validate(nested)


class ActionUpdate(BaseModel):
    customer_id: str
    action_id: str
    status: Literal["contacted", "accepted", "declined"]
    note: str | None = Field(None, max_length=500)


class Reason(BaseModel):
    feature: str
    category: str
    value: str | int | float
    impact: float
    direction: str

    @field_validator("value", mode="before")
    @classmethod
    def _stringify(cls, v):
        return v if isinstance(v, (int, float, str)) else str(v)


class Prediction(BaseModel):
    churn_probability: float
    risk_band: Literal["low", "medium", "high"]
    will_churn: bool
    threshold: float
    model: str
    model_used: Literal["profile", "survey"]
    reasons: list[Reason] = []
