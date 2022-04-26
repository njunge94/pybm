from functools import partial
from typing import Optional, Any, Dict, List, Callable

from pybm.io.json import JSONFileIO
from pybm.reporters.base import BaseReporter
from pybm.reporters.util import (
    groupby,
    log_to_console,
    reduce,
    rescale,
    sort_benchmark,
    transform_key,
)
from pybm.util.common import (
    dfilter_regex,
    dvmap,
    flatten,
    lmap,
)
from pybm.util.formatting import (
    format_benchmark,
    format_ref,
    format_relative,
    format_speedup,
    format_time,
)
from pybm.util.path import get_subdirs


def process(bm: Dict[str, Any], target_time_unit: str, shalength: int):
    """
    Process benchmark dict with its associated context. Order matters on
    construction - name and ref should come first, then timings, then iteration
    counts, then user context, then metrics.
    """
    bm["name"] = format_benchmark(bm.pop("name"), bm.pop("executable"))
    bm["reference"] = format_ref(bm.pop("ref"), bm.pop("commit"), shalength=shalength)

    time_unit: Optional[str] = bm.pop("time_unit", None)

    if time_unit is not None:
        time_values: Dict[str, Any] = dfilter_regex(".*time", bm)

        rescale_fn = partial(
            rescale, current_unit=time_unit, target_unit=target_time_unit
        )

        bm.update(dvmap(rescale_fn, time_values))

    return bm


def compare(results: List[Dict[str, Any]]):
    """Compare results between different refs with respect to an anchor ref. Assumes
    that the results are sorted in the same order."""
    if len(results) == 1:
        return results

    anchor_result = results[0]

    for result in results:
        relative = {}
        for k, v in result.items():
            if isinstance(v, tuple):
                # relative time difference and speedup w.r.t anchor ref
                speedup = anchor_result[k][0] / v[0]
                relative["speedup"] = speedup
            elif isinstance(v, float):
                speedup = anchor_result[k] / v
            else:
                continue

            relative[f"Δ {k}"] = 1.0 / speedup - 1.0

        # add relative differences to the result
        result.update(relative)

    return results


class JSONConsoleReporter(BaseReporter):
    def __init__(self):
        super(JSONConsoleReporter, self).__init__()

        # file IO for reading / writing JSON files
        self.io = JSONFileIO(result_dir=self.result_dir)  # type: ignore
        self.padding = 1
        # formatters for the data table
        self.formatters: Dict[str, Callable[[Any], str]] = {
            "time": partial(
                format_time,
                unit=self.target_time_unit,
                digits=self.significant_digits,
            ),
            "relative": partial(format_relative, digits=self.significant_digits),
            "speedup": partial(format_speedup, digits=self.significant_digits),
        }

    def compare(
        self,
        *refs: str,
        absolute: bool = False,
        previous: int = 1,
        target_filter: Optional[str] = None,
        benchmark_filter: Optional[str] = None,
        context_filter: Optional[str] = None,
    ):
        results = sorted(get_subdirs(self.result_dir), key=int)[: -previous - 1 : -1]

        benchmarks = []
        for result in results:
            benchmarks += self.read(
                *refs,
                result=result,
                target_filter=target_filter,
                benchmark_filter=benchmark_filter,
                context_filter=context_filter,
            )

        # aggregate results with the same name and commit
        reduced = [reduce(group) for group in groupby(["name", "commit"], benchmarks)]

        process_fn = partial(
            process,
            target_time_unit=self.target_time_unit,
            shalength=self.shalength,
        )

        processed_results = lmap(process_fn, reduced)

        # group results again by benchmark name
        grouped_results = groupby("name", processed_results)

        if absolute:
            compared_results = flatten(grouped_results)
        else:
            compared_results = flatten(map(compare, grouped_results))

        transform_fn = partial(self.transform_result, anchor_ref=refs[0])
        formatted_results = lmap(transform_fn, compared_results)

        log_to_console(formatted_results, padding=self.padding)
        # TODO: Print summary about improvements etc.

    def transform_result(self, bm: Dict[str, Any], anchor_ref: str) -> Dict[str, str]:
        """
        Finalize column header names, cast values to string, and optionally format.
        """
        sorted_bm = sort_benchmark(bm)
        transformed = {}

        for key, value in sorted_bm.items():
            tkey = transform_key(key)
            if key.startswith("Δ"):
                tkey += f" ({anchor_ref})"
                value_type = "relative"
            elif key.endswith("time"):
                tkey += f" ({self.target_time_unit})"
                value_type = "time"
            else:
                value_type = key

            transformed[tkey] = self.formatters.get(value_type, str)(value)

        return transformed
