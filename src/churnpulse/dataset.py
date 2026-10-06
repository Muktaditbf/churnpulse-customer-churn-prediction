"""IBM Telco Customer Churn v11.1.3: download, verify, merge, add identities.

The five IBM tables (demographics, location, population, services, status)
are merged into one customer table with clean snake_case columns grouped by
persona category. Names, emails and phone numbers are generated (the dataset
has none) - they are for display only and are never used by the model.

    python -m churnpulse.dataset      # download + build data/processed/customers.csv
"""

from __future__ import annotations

import hashlib
import logging
import urllib.request

import pandas as pd

from . import config

log = logging.getLogger("churnpulse.dataset")

# A public mirror of IBM's Telco Customer Churn v11.1.3, pinned to one commit
# and verified by checksum so every download is byte-for-byte identical.
SOURCE = ("https://raw.githubusercontent.com/wasifmaqsood/IBM-Telco-Customer-Churn-Project-MySql/"
          "f87e88e13fecbd2a4000fe876bbe60ab19c45284/Telco_customer_churn_{table}.csv")
CHECKSUMS = {
    "demographics": "a17d2c46e14a6ef4da609eca787da1298c6561744c9f0bd9d0c8d82015ef4e26",
    "location": "11c42854c09bb458c2952c39b5964dec8b023bc83ca7ff0fe1240c6a885f377f",
    "population": "41f3140b6e0507e133d1e8d91612eeba0b8b3b2c7a2d08fa19230b11b0b71b17",
    "services": "bc79dca46564018569666aa38a90db884298ab08042af1e8a960b225e8705a0d",
    "status": "96f6f06d0c6f239ccba399758c305c2d613789708c876b63a01fbc1a934be1b0",
}

# IBM column -> ChurnPulse column
RENAME = {
    "Customer ID": "customer_id",
    # geographic
    "City": "city", "Zip Code": "zip_code", "Latitude": "latitude", "Longitude": "longitude",
    "Population": "population",
    # demographic
    "Gender": "gender", "Age": "age", "Married": "married", "Number of Dependents": "num_dependents",
    # technographic
    "Phone Service": "phone_service", "Multiple Lines": "multiple_lines", "Internet Type": "internet_type",
    "Avg Monthly GB Download": "avg_monthly_gb", "Unlimited Data": "unlimited_data",
    "Online Security": "online_security", "Online Backup": "online_backup",
    "Device Protection Plan": "device_protection", "Premium Tech Support": "premium_tech_support",
    "Streaming TV": "streaming_tv", "Streaming Movies": "streaming_movies", "Streaming Music": "streaming_music",
    # behavioural
    "Tenure in Months": "tenure_months", "Contract": "contract", "Payment Method": "payment_method",
    "Paperless Billing": "paperless_billing", "Offer": "offer", "Number of Referrals": "referrals",
    "Monthly Charge": "monthly_charge", "Total Charges": "total_charges", "Total Refunds": "total_refunds",
    "Total Extra Data Charges": "total_extra_data_charges",
    "Avg Monthly Long Distance Charges": "avg_long_distance",
    "Total Long Distance Charges": "total_long_distance_charges",
    # psychographic
    "Satisfaction Score": "satisfaction_score",
    # value (display / business only - never a model input)
    "CLTV": "cltv",
    # label
    "Churn Value": "churned",
}

YES_NO = ["married", "phone_service", "multiple_lines", "unlimited_data", "online_security", "online_backup",
          "device_protection", "premium_tech_support", "streaming_tv", "streaming_movies", "streaming_music",
          "paperless_billing"]

# Columns that are only known after a customer has left (or are IBM's own
# churn model output). They must never reach a model - a test enforces it.
LEAKY_COLUMNS = ["Churn Score", "Churn Category", "Churn Reason", "Customer Status", "Churn Label",
                 "Churn Value", "Count", "Quarter", "CLTV"]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(force: bool = False) -> None:
    config.DATA_V11.mkdir(parents=True, exist_ok=True)
    for table, expected in CHECKSUMS.items():
        path = config.DATA_V11 / f"{table}.csv"
        if path.exists() and not force and _sha256(path.read_bytes()) == expected:
            continue
        with urllib.request.urlopen(SOURCE.format(table=table), timeout=60) as response:
            data = response.read()
        if _sha256(data) != expected:
            raise ValueError(f"checksum mismatch for {table}.csv - the source file changed")
        path.write_bytes(data)
        log.info("downloaded %s.csv (%d bytes)", table, len(data))


def merge_tables() -> pd.DataFrame:
    """The five IBM tables -> one row per customer with ChurnPulse columns."""
    read = lambda t: pd.read_csv(config.DATA_V11 / f"{t}.csv")  # noqa: E731
    keys = ["Customer ID", "Count"]
    df = (read("demographics")
          .merge(read("location"), on=keys)
          .merge(read("services"), on=keys)
          .merge(read("status"), on=keys + ["Quarter"])
          .merge(read("population")[["Zip Code", "Population"]], on="Zip Code", how="left"))
    df = df[list(RENAME)].rename(columns=RENAME)

    for col in YES_NO:
        df[col] = df[col].eq("Yes")
    df["offer"] = df["offer"].fillna("None")
    df["internet_type"] = df["internet_type"].fillna("None")
    # Population is stored as text with thousands separators ("68,701").
    population = pd.to_numeric(df["population"].astype(str).str.replace(",", ""), errors="coerce")
    df["population"] = population.fillna(population.median()).astype(int)
    df["zip_code"] = df["zip_code"].astype(str)
    df["churned"] = df["churned"].astype(int)
    return df


def add_identities(df: pd.DataFrame) -> pd.DataFrame:
    """Realistic, deterministic names and contact details (display only)."""
    from faker import Faker

    fake = Faker("en_US")
    names, emails, phones = [], [], []
    for cid, gender in zip(df["customer_id"], df["gender"], strict=True):
        fake.seed_instance(int(hashlib.md5(cid.encode()).hexdigest()[:8], 16))
        first = fake.first_name_female() if gender == "Female" else fake.first_name_male()
        last = fake.last_name()
        names.append(f"{first} {last}")
        # Reserved example domains and the fictional 555-01xx range, so no
        # generated contact can belong to a real person.
        domain = fake.random_element(["example.com", "example.net", "example.org"])
        emails.append(f"{first}.{last}{fake.random_int(1, 99)}@{domain}".lower())
        phones.append(f"({fake.numerify('###')}) 555-01{fake.numerify('##')}")
    out = df.copy()
    out.insert(1, "name", names)
    out.insert(2, "email", emails)
    out.insert(3, "phone", phones)
    return out


def build() -> pd.DataFrame:
    download()
    df = add_identities(merge_tables())
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.CUSTOMERS_CSV, index=False)
    log.info("wrote %s (%d customers, %d columns)", config.CUSTOMERS_CSV, len(df), df.shape[1])
    return df


def load_customers() -> pd.DataFrame:
    """The processed customer table (run ``build()`` / ``make data`` first)."""
    return pd.read_csv(config.CUSTOMERS_CSV, dtype={"zip_code": str})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    build()
