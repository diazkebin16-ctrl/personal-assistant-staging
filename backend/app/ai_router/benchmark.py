"""Offline benchmark fixtures for a future GPT-5 Nano versus Luna evaluation."""

from dataclasses import dataclass

from backend.app.ai_router.enums import Complexity


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    key: str
    prompt: str
    complexity: Complexity
    output_token_budget: int
    prior_context: tuple[str, ...] = ()
    requires_stronger_reasoning: bool = False


NANO_LUNA_BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase("greeting", "Hola, ¿cómo estás?", Complexity.TRIVIAL, 128),
    BenchmarkCase("simple_fact", "¿Cuál es la capital de Francia?", Complexity.LOW, 128),
    BenchmarkCase("short_explanation", "Explica brevemente qué es una API.", Complexity.LOW, 256),
    BenchmarkCase("rewrite", "Reformula: El envío llegó tarde pero completo.", Complexity.LOW, 256),
    BenchmarkCase(
        "intent", "Clasifica la intención: recuérdame llamar a Ana mañana.", Complexity.LOW, 128
    ),
    BenchmarkCase("extract", "Extrae nombre y ciudad: Marta vive en Boston.", Complexity.LOW, 128),
    BenchmarkCase(
        "short_summary",
        "Resume en dos frases: Lex debe usar el contexto mínimo suficiente y respetar permisos.",
        Complexity.LOW,
        256,
    ),
    BenchmarkCase(
        "recent_follow_up",
        "¿Y cuánto cuesta?",
        Complexity.LOW,
        128,
        prior_context=("El plan cuesta 20 dólares al mes.",),
    ),
    BenchmarkCase(
        "allowed_context",
        "De esas opciones, ¿cuál recomiendas?",
        Complexity.LOW,
        256,
        prior_context=("Opción A prioriza velocidad; opción B prioriza calidad.",),
    ),
    BenchmarkCase(
        "strong_reasoning_boundary",
        "Compara tres arquitecturas distribuidas con fallos parciales y justifica la mejor bajo restricciones contradictorias.",
        Complexity.HIGH,
        512,
        requires_stronger_reasoning=True,
    ),
)
