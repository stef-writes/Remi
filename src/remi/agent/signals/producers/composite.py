"""CompositeProducer — runs multiple SignalProducers and merges their results.

Top-level entry point for running a pluggable pipeline of signal sources:

    composite = CompositeProducer(signal_store, [
        StatisticalProducer(knowledge_graph=knowledge_graph),
        CompositionProducer(domain=domain, signal_store=signal_store),
    ])
    result = await composite.run_all()

All producers run sequentially (order matters for deduplication). Results
are merged into the SignalStore. Duplicate signal IDs from later producers
are skipped — earlier producers win.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from remi.agent.observe.types import SpanKind, Tracer
from remi.agent.signals.persistence.stores import SignalStore
from remi.agent.signals.signal import ProducerResult, Signal, SignalProducer

_log = structlog.get_logger(__name__)


@dataclass
class CompositeResult:
    """Merged output from all signal producers."""

    produced: int = 0
    retired: int = 0
    unchanged: int = 0
    errors: int = 0
    signals: list[Signal] = field(default_factory=list)
    trace_id: str | None = None
    per_source: dict[str, ProducerResult] = field(default_factory=dict)
    failed_producers: list[str] = field(default_factory=list)


class CompositeProducer:
    """Runs multiple SignalProducers in sequence, merges into SignalStore."""

    def __init__(
        self,
        signal_store: SignalStore,
        producers: list[SignalProducer] | None = None,
        *,
        tracer: Tracer | None = None,
    ) -> None:
        self._ss = signal_store
        self._producers: list[SignalProducer] = list(producers or [])
        self._tracer = tracer

    def add_producer(self, producer: SignalProducer) -> None:
        self._producers.append(producer)

    @property
    def producers(self) -> list[SignalProducer]:
        return list(self._producers)

    async def run_all(self) -> CompositeResult:
        if self._tracer is not None:
            return await self._run_all_traced()
        return await self._run_all_core()

    async def _run_all_core(self) -> CompositeResult:
        await self._ss.clear_all()
        result = CompositeResult()
        seen_ids: set[str] = set()

        for producer in self._producers:
            _log.info("producer_starting", producer=producer.name)
            try:
                pr = await producer.evaluate()
                pr.source = producer.name
                result.per_source[producer.name] = pr

                for sig in pr.signals:
                    if sig.signal_id in seen_ids:
                        _log.debug(
                            "signal_deduplicated",
                            signal_id=sig.signal_id,
                            source=producer.name,
                        )
                        continue
                    seen_ids.add(sig.signal_id)
                    await self._ss.put_signal(sig)
                    result.signals.append(sig)
                    result.produced += 1

                _log.info(
                    "producer_complete",
                    producer=producer.name,
                    produced=pr.produced,
                    errors=pr.errors,
                )
            except Exception:
                result.errors += 1
                result.failed_producers.append(producer.name)
                _log.warning(
                    "producer_failed",
                    producer=producer.name,
                    exc_info=True,
                )

        _log.info(
            "composite_production_complete",
            total_produced=result.produced,
            sources=len(self._producers),
        )
        return result

    async def _run_all_traced(self) -> CompositeResult:
        assert self._tracer is not None
        async with self._tracer.start_trace(
            "signals.composite",
            kind=SpanKind.SIGNAL_PRODUCTION,
            producer_count=len(self._producers),
            producer_names=[p.name for p in self._producers],
        ) as trace_ctx:
            await self._ss.clear_all()
            result = CompositeResult()
            result.trace_id = trace_ctx.trace_id
            seen_ids: set[str] = set()

            for producer in self._producers:
                async with trace_ctx.span(
                    SpanKind.SIGNAL_PRODUCTION,
                    f"producer:{producer.name}",
                    producer_name=producer.name,
                ) as prod_ctx:
                    try:
                        pr = await producer.evaluate()
                        pr.source = producer.name
                        result.per_source[producer.name] = pr
                        prod_ctx.set_attribute("produced", pr.produced)
                        prod_ctx.set_attribute("errors", pr.errors)

                        for sig in pr.signals:
                            if sig.signal_id in seen_ids:
                                continue
                            seen_ids.add(sig.signal_id)
                            await self._ss.put_signal(sig)
                            result.signals.append(sig)
                            result.produced += 1
                            prod_ctx.add_event(
                                "signal_produced",
                                signal_type=sig.signal_type,
                                entity_id=sig.entity_id,
                                severity=sig.severity.value,
                                provenance=sig.provenance.value,
                            )
                    except Exception as exc:
                        result.errors += 1
                        result.failed_producers.append(producer.name)
                        prod_ctx.set_attribute("error", str(exc))
                        _log.warning(
                            "producer_failed",
                            producer=producer.name,
                            exc_info=True,
                        )

            trace_ctx.set_attribute("total_produced", result.produced)
            return result


