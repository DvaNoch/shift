import datetime as dt
import json
import sqlite3
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from .models import Payment, PaymentTotals, Summary, Trip, TripIn


class TripConflict(Exception):
    """Поездка с таким id уже есть, но с другими данными."""

    def __init__(self, trip_id: str, fields: list[str]):
        super().__init__(f"поездка {trip_id} уже сохранена с другими данными: {', '.join(fields)}")
        self.trip_id = trip_id
        self.fields = fields


class SeedError(Exception):
    """Файл с начальными поездками нельзя загрузить."""


def to_tiyn(value: Decimal) -> int:
    # Модель гарантирует не больше двух знаков после запятой, поэтому перевод точный.
    return int(value * 100)


def from_tiyn(value: int) -> Decimal:
    return Decimal(value).scaleb(-2)


def local_day(start: dt.datetime) -> dt.date:
    # date() у datetime со смещением — дата в его собственном поясе, а не в UTC.
    return start.date()


def _utc_key(moment: dt.datetime) -> str:
    # Фиксированная ширина, чтобы строки сортировались как время.
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")


def _stored_values(trip: TripIn) -> dict:
    """Нормализованные данные поездки: по ним же сравниваются повторные отправки."""
    return {
        "start": trip.start.isoformat(),
        "end": trip.end.isoformat(),
        "amount": to_tiyn(trip.amount),
        "payment": trip.payment.value,
        "commission": to_tiyn(trip.commission),
    }


def _row_values(row: sqlite3.Row) -> dict:
    return {
        "start": row["start_at"],
        "end": row["end_at"],
        "amount": row["amount_tiyn"],
        "payment": row["payment"],
        "commission": row["commission_tiyn"],
    }


def _row_to_trip(row: sqlite3.Row) -> Trip:
    return Trip(
        id=row["id"],
        start=dt.datetime.fromisoformat(row["start_at"]),
        end=dt.datetime.fromisoformat(row["end_at"]),
        amount=from_tiyn(row["amount_tiyn"]),
        payment=row["payment"],
        commission=from_tiyn(row["commission_tiyn"]),
        local_date=dt.date.fromisoformat(row["local_date"]),
    )


def add_trip(conn: sqlite3.Connection, trip: TripIn) -> tuple[Trip, bool]:
    """Сохраняет поездку. Возвращает (поездка, создана ли она сейчас).

    Повтор с теми же данными возвращает существующую запись, с другими — TripConflict.
    Транзакцией управляет вызывающий код.
    """
    values = _stored_values(trip)
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO trips
            (id, start_at, end_at, start_utc, local_date, amount_tiyn, payment, commission_tiyn)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trip.id,
            values["start"],
            values["end"],
            _utc_key(trip.start),
            local_day(trip.start).isoformat(),
            values["amount"],
            values["payment"],
            values["commission"],
        ),
    )
    created = cur.rowcount == 1
    row = conn.execute("SELECT * FROM trips WHERE id = ?", (trip.id,)).fetchone()
    if not created:
        existing = _row_values(row)
        changed = [field for field in values if existing[field] != values[field]]
        if changed:
            raise TripConflict(trip.id, changed)
    return _row_to_trip(row), created


def trips_for_day(conn: sqlite3.Connection, day: dt.date) -> list[Trip]:
    rows = conn.execute(
        "SELECT * FROM trips WHERE local_date = ? ORDER BY start_utc, id",
        (day.isoformat(),),
    ).fetchall()
    return [_row_to_trip(row) for row in rows]


def summarize(day: dt.date, trips: Iterable[TripIn]) -> Summary:
    totals = {
        Payment.cash: {"trips": 0, "revenue": Decimal(0)},
        Payment.card: {"trips": 0, "revenue": Decimal(0)},
    }
    commission = Decimal(0)
    for trip in trips:
        totals[trip.payment]["trips"] += 1
        totals[trip.payment]["revenue"] += trip.amount
        commission += trip.commission

    revenue = totals[Payment.cash]["revenue"] + totals[Payment.card]["revenue"]
    return Summary(
        date=day,
        trips=totals[Payment.cash]["trips"] + totals[Payment.card]["trips"],
        revenue=revenue,
        commission=commission,
        net=revenue - commission,
        cash=PaymentTotals(**totals[Payment.cash]),
        card=PaymentTotals(**totals[Payment.card]),
    )


def seed_from_file(conn: sqlite3.Connection, path: Path) -> int:
    """Загружает поездки из JSON-файла. Возвращает число новых записей."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SeedError(f"не удалось прочитать {path}: {exc}") from exc
    if not isinstance(raw, list):
        raise SeedError(f"{path}: ожидался JSON-массив поездок")

    created = 0
    for number, item in enumerate(raw, start=1):
        label = f"запись №{number}"
        if isinstance(item, dict) and "id" in item:
            label += f" (id={item['id']})"
        try:
            _, is_new = add_trip(conn, TripIn.model_validate(item))
        except ValidationError as exc:
            raise SeedError(f"{path.name}: {label} не прошла проверку:\n{exc}") from exc
        except TripConflict as exc:
            raise SeedError(f"{path.name}: {label}: {exc}") from exc
        created += is_new
    return created


def seed_once(conn: sqlite3.Connection, path: Path) -> int:
    """Загружает trips.json при первом запуске; повторные запуски его не трогают."""
    if conn.execute("SELECT 1 FROM meta WHERE key = 'seeded'").fetchone():
        return 0
    if not path.exists():
        return 0
    with conn:
        created = seed_from_file(conn, path)
        conn.execute("INSERT INTO meta (key, value) VALUES ('seeded', ?)", (path.name,))
    return created
