from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from app.models.acts import Act, ActLine
from app.models.directories import Contract, Project
from app.reports.act_excel import build_act_workbook


def _make_act_with_lines():
    project = Project(id=uuid.uuid4(), code="P-1", name="ЖК Тестовый")
    contract = Contract(id=uuid.uuid4(), project_id=project.id, number="Д-42")
    act = Act(
        id=uuid.uuid4(),
        project_id=project.id,
        contract_id=contract.id,
        act_number="7",
        act_date=dt.date(2026, 9, 21),
        status="finalized",
        total_amount=Decimal("15000.00"),
    )
    lines = [
        ActLine(
            id=uuid.uuid4(),
            act_id=act.id,
            work_entry_id=uuid.uuid4(),
            accepted_volume=Decimal("10.000"),
            unit_price=Decimal("500.00"),
            amount=Decimal("5000.00"),
            work_type_name="Штукатурка стен",
            unit_name="м2",
            location_snapshot="этаж 3, пом. 301",
            comment="Без замечаний",
        ),
        ActLine(
            id=uuid.uuid4(),
            act_id=act.id,
            work_entry_id=uuid.uuid4(),
            accepted_volume=Decimal("20.000"),
            unit_price=Decimal("500.00"),
            amount=Decimal("10000.00"),
            work_type_name="Штукатурка стен",
            unit_name="м2",
            location_snapshot="этаж 4, пом. 401",
            comment=None,
        ),
    ]
    return act, lines, project, contract


def test_excel_generation_has_expected_headers_and_values():
    act, lines, project, contract = _make_act_with_lines()

    workbook = build_act_workbook(act, lines, project, contract)
    sheet = workbook.active

    header_row = 4
    headers = [sheet.cell(row=header_row, column=col).value for col in range(1, 11)]
    assert headers == [
        "№",
        "Объект",
        "Договор/раздел",
        "Вид работы",
        "Место выполнения",
        "Ед. изм.",
        "Объём",
        "Цена",
        "Сумма",
        "Комментарий",
    ]

    assert sheet.cell(row=header_row + 1, column=4).value == "Штукатурка стен"
    assert sheet.cell(row=header_row + 1, column=7).value == 10.0
    assert sheet.cell(row=header_row + 1, column=9).value == 5000.0

    total_row = header_row + 1 + len(lines)
    assert sheet.cell(row=total_row, column=9).value == 15000.0
    assert sheet.cell(row=total_row, column=9).number_format == '#,##0.00" ₸"'

    assert sheet.freeze_panes == f"A{header_row + 1}"
    assert sheet.auto_filter.ref is not None


def test_excel_column_widths_are_capped():
    act, lines, project, contract = _make_act_with_lines()
    lines[0].comment = "x" * 500

    workbook = build_act_workbook(act, lines, project, contract)
    sheet = workbook.active

    for dimension in sheet.column_dimensions.values():
        if dimension.width is not None:
            assert dimension.width <= 60
