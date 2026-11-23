"""Synthetic case families with different worksheet and agent workflows."""

from random import choice, randint

from respira.scales import EXAMPLE

PROFILES = {
    "hypoxemia": {
        "title": "Острая гипоксемия",
        "description": "Взрослый с одышкой получает кислород. Сопоставьте оксигенацию с NEWS2.",
        "targets": (("stdio", "pf_ratio"), ("sse", "news2")),
        "prompt": "Рассчитай PaO₂/FiO₂ через stdio и NEWS2 через SSE. Затем найди в PubMed три статьи о высокопоточной оксигенации при острой гипоксемической дыхательной недостаточности. Укажи PMID.",
        "research": "acute hypoxemic respiratory failure high-flow nasal cannula",
    },
    "pneumonia": {
        "title": "Подозрение на пневмонию",
        "description": "Учебный случай с лихорадкой и учащенным дыханием. Сравните, какие признаки учитывают две шкалы.",
        "targets": (("stdio", "curb65"), ("sse", "qsofa")),
        "prompt": "Для текущего случая рассчитай CURB-65 через stdio и qSOFA через SSE. Сравни вклад частоты дыхания, давления и сознания в обе шкалы. Поиск статей для этого задания не нужен.",
        "research": "community-acquired pneumonia CURB-65",
    },
    "high_flow": {
        "title": "На высокопоточной оксигенации",
        "description": "Взрослый уже получает HFNC. Сопоставьте два индекса и подберите статьи по теме.",
        "targets": (("sse", "rox"), ("stdio", "pf_ratio")),
        "prompt": "Рассчитай текущий ROX через SSE и PaO₂/FiO₂ через stdio. Затем найди в PubMed две статьи об отлучении от HFNC у взрослых и укажи PMID. Объясни, какие данные понадобятся для сравнения ROX в динамике.",
        "research": "high-flow nasal cannula weaning adults",
    },
    "hypercapnia": {
        "title": "NEWS2 при риске гиперкапнии",
        "description": "В случае явно назначена шкала SpO₂ 2. Сравните ее со шкалой 1 на тех же измерениях.",
        "targets": (("sse", "news2"), ("stdio", "pf_ratio")),
        "prompt": "Сравни две оценки NEWS2 через SSE на одних и тех же показателях. Сначала вызови шкалу SpO₂ 2, которая указана в случае, затем отдельно шкалу 1 как учебное сравнение. Покажи, какой компонент и почему изменился. Поиск статей не нужен.",
        "research": "hypercapnic respiratory failure NEWS2 oxygen saturation",
    },
}


def build_scenario(profile="hypoxemia", *, vary=False):
    values = dict(EXAMPLE)
    if profile == "pneumonia":
        confusion = choice((False, True)) if vary else False
        values.update(
            age=randint(62, 82) if vary else 69,
            urea=(randint(64, 105) / 10) if vary else 8.4,
            resp_rate=randint(27, 34) if vary else 31,
            systolic=randint(92, 117) if vary else 98,
            diastolic=randint(59, 76) if vary else 65,
            confusion=confusion,
            altered_mentation=confusion,
        )
    elif profile == "high_flow":
        values.update(
            pao2=randint(62, 82) if vary else 73,
            fio2=(randint(45, 65) / 100) if vary else .5,
            spo2=randint(91, 96) if vary else 94,
            resp_rate=randint(24, 32) if vary else 27,
        )
    elif profile == "hypercapnia":
        values.update(
            pao2=randint(58, 68) if vary else 64,
            fio2=.28,
            spo2=randint(88, 91) if vary else 90,
            resp_rate=randint(20, 26) if vary else 22,
            pulse=randint(76, 98) if vary else 90,
            spo2_scale="2",
            temp=36.8,
        )
    elif vary:
        values.update(
            pao2=randint(72, 84), fio2=(randint(35, 45) / 100),
            spo2=randint(92, 95), resp_rate=randint(22, 27), pulse=randint(83, 97),
        )
    return {"id": profile, **PROFILES[profile], "values": values}


def next_scenario(previous):
    return build_scenario(choice([key for key in PROFILES if key != previous]), vary=True)
