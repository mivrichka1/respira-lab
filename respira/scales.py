"""Deterministic adult respiratory teaching scales."""

from typing import Annotated, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field, StrictBool

Age = Annotated[int, Field(strict=True, ge=18, le=120, title="Возраст", json_schema_extra={"unit": "лет"})]
PaO2 = Annotated[float, Field(strict=True, ge=10, le=800, title="PaO₂", json_schema_extra={"unit": "мм рт. ст."})]
FiO2 = Annotated[float, Field(strict=True, ge=.21, le=1, title="FiO₂", description="Доля от 0,21 до 1", json_schema_extra={"unit": "доля"})]
SpO2 = Annotated[int, Field(strict=True, ge=30, le=100, title="SpO₂", json_schema_extra={"unit": "%"})]
Breaths = Annotated[int, Field(strict=True, ge=1, le=100, title="Частота дыхания", json_schema_extra={"unit": "в мин"})]
Systolic = Annotated[int, Field(strict=True, ge=35, le=300, title="Систолическое давление", json_schema_extra={"unit": "мм рт. ст."})]
Diastolic = Annotated[int, Field(strict=True, ge=15, le=200, title="Диастолическое давление", json_schema_extra={"unit": "мм рт. ст."})]
Pulse = Annotated[int, Field(strict=True, ge=20, le=300, title="Пульс", json_schema_extra={"unit": "в мин"})]
Temperature = Annotated[float, Field(strict=True, ge=25, le=45, title="Температура", json_schema_extra={"unit": "°C"})]
Urea = Annotated[float, Field(strict=True, ge=.1, le=100, title="Мочевина", json_schema_extra={"unit": "ммоль/л"})]
Oxygen = Annotated[StrictBool, Field(title="Дополнительный кислород")]
Confusion = Annotated[StrictBool, Field(title="Новая спутанность сознания")]
Altered = Annotated[StrictBool, Field(title="Измененное сознание")]
Consciousness = Annotated[Literal["alert", "confused", "voice", "pain", "unresponsive"], Field(title="Сознание (ACVPU)")]
OximetryScale = Annotated[Literal["1", "2"], Field(title="Шкала SpO₂", description="Для шкалы 2 требуется явное назначение клинициста")]

METHODS = {
    "pf_ratio": ("PaO₂/FiO₂", "Оксигенация", "https://doi.org/10.1001/jama.2012.5669"),
    "curb65": ("CURB-65", "Пульмонология", "https://doi.org/10.1136/thorax.58.5.377"),
    "qsofa": ("qSOFA", "Инфекционные состояния", "https://doi.org/10.1001/jama.2016.0287"),
    "news2": ("NEWS2", "Неотложная оценка", "https://www.rcp.ac.uk/resources/national-early-warning-score-news-2/"),
    "rox": ("Индекс ROX", "Респираторная поддержка", "https://pubmed.ncbi.nlm.nih.gov/30576221/"),
}

# These values belong to one synthetic case only. UI and client use the same preset.
EXAMPLE = {
    "pao2": 80, "fio2": .40, "spo2": 94, "resp_rate": 24, "pulse": 88,
    "supplemental_oxygen": True, "systolic": 105, "diastolic": 66, "temp": 38.3,
    "consciousness": "alert", "spo2_scale": "1", "age": 67, "urea": 7.4,
    "confusion": False, "altered_mentation": False,
}


def score_result(tool, value, unit, components, guidance, category=None, tone="neutral"):
    title, specialty, source = METHODS[tool]
    return {
        "title": title, "specialty": specialty, "value": round(value, 2), "unit": unit,
        "components": components, "guidance": guidance, "category": category, "tone": tone, "source": source,
    }


def pf_ratio(pao2: PaO2, fio2: FiO2) -> dict:
    """Делит артериальное PaO₂ в мм рт. ст. на FiO₂, заданную долей."""
    return score_result("pf_ratio", pao2 / fio2, "мм рт. ст.",
                        {"PaO₂": pao2, "FiO₂": fio2, "Формула": "PaO₂ / FiO₂"},
                        "Интерпретируйте вместе с условиями респираторной поддержки и остальными критериями.")


def curb65(confusion: Confusion, urea: Urea, resp_rate: Breaths,
           systolic: Systolic, diastolic: Diastolic, age: Age) -> dict:
    """Оценивает тяжесть внебольничной пневмонии у взрослых по пяти признакам."""
    if diastolic >= systolic:
        raise ToolError("Диастолическое давление должно быть ниже систолического.")
    points = {
        "Спутанность сознания": int(confusion), "Мочевина > 7 ммоль/л": int(urea > 7),
        "Частота дыхания ≥ 30": int(resp_rate >= 30),
        "САД < 90 или ДАД ≤ 60": int(systolic < 90 or diastolic <= 60), "Возраст ≥ 65": int(age >= 65),
    }
    score = sum(points.values())
    category, tone = ("Низкая группа риска", "green") if score < 2 else (
        ("Промежуточная группа риска", "amber") if score == 2 else ("Высокая группа риска", "red")
    )
    return score_result("curb65", score, "из 5", points,
                        "Сопоставьте группу с клинической картиной и действующим протоколом ведения пневмонии.",
                        category, tone)


def qsofa(resp_rate: Breaths, systolic: Systolic, altered_mentation: Altered) -> dict:
    """Считает три признака qSOFA для взрослого при подозрении на инфекцию."""
    points = {
        "Частота дыхания ≥ 22": int(resp_rate >= 22), "САД ≤ 100": int(systolic <= 100),
        "Измененное сознание": int(altered_mentation),
    }
    score = sum(points.values())
    return score_result("qsofa", score, "из 3", points,
                        "При двух и более признаках уместна дополнительная клиническая оценка. Шкала не определяет диагноз.",
                        "Два и более признака" if score >= 2 else "Меньше двух признаков",
                        "amber" if score >= 2 else "neutral")


def band(value, thresholds):
    """Lookup ordered inclusive upper bounds and a final catch-all."""
    for ceiling, points in thresholds:
        if value <= ceiling:
            return points
    raise ValueError("Значение вне шкалы.")


def news2(resp_rate: Breaths, spo2: SpO2, spo2_scale: OximetryScale,
          supplemental_oxygen: Oxygen, systolic: Systolic, pulse: Pulse,
          consciousness: Consciousness, temp: Temperature) -> dict:
    """Суммирует все компоненты NEWS2. Шкалу SpO₂ выбирают явно."""
    if spo2_scale == "1":
        saturation = band(spo2, [(91, 3), (93, 2), (95, 1), (100, 0)])
    else:
        saturation = band(spo2, [(83, 3), (85, 2), (87, 1), (92, 0), (100, 0)])
        if supplemental_oxygen and spo2 >= 93:
            saturation = band(spo2, [(94, 1), (96, 2), (100, 3)])
    points = {
        "Частота дыхания": band(resp_rate, [(8, 3), (11, 1), (20, 0), (24, 2), (100, 3)]),
        f"SpO₂ · шкала {spo2_scale}": saturation,
        "Дополнительный кислород": 2 if supplemental_oxygen else 0,
        "Систолическое давление": band(systolic, [(90, 3), (100, 2), (110, 1), (219, 0), (300, 3)]),
        "Пульс": band(pulse, [(40, 3), (50, 1), (90, 0), (110, 1), (130, 2), (300, 3)]),
        "Сознание": 0 if consciousness == "alert" else 3,
        "Температура": band(round(temp, 1), [(35, 3), (36, 1), (38, 0), (39, 1), (45, 2)]),
    }
    score = sum(points.values())
    if score >= 7:
        category, tone, guidance = "Высокий риск", "red", "NEWS2 ≥ 7 соответствует экстренной клинической оценке по протоколу учреждения."
    elif score >= 5 or max(points.values()) == 3:
        category, tone, guidance = "Требуется оценка", "amber", "Оцените динамику и действуйте по локальному протоколу эскалации NEWS2."
    else:
        category, tone, guidance = "Низкая группа риска", "green", "Продолжайте оценку динамики по локальному протоколу и учитывайте клинический контекст."
    return score_result("news2", score, "баллов", points, guidance, category, tone)


def rox(spo2: SpO2, fio2: FiO2, resp_rate: Breaths) -> dict:
    """Вычисляет ROX как (SpO₂ в процентах / FiO₂ долей) / частоту дыхания."""
    return score_result("rox", (spo2 / fio2) / resp_rate, "",
                        {"SpO₂, %": spo2, "FiO₂": fio2, "Частота дыхания, в мин": resp_rate},
                        "Оценивайте динамику и время от начала высокопоточной терапии. Порог зависит от времени измерения.")


STDIO_SCALES = (pf_ratio, curb65, qsofa)
SSE_SCALES = (*STDIO_SCALES, news2, rox)
