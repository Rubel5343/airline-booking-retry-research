#!/usr/bin/env python3
from dataclasses import dataclass

@dataclass(frozen=True)
class Scenario:
    supplier_completion_ms: int
    client_timeout_ms: int
    visibility_delay_ms: int = 0
    retry_processing_ms: int | None = None

    @property
    def first_visible_ms(self) -> int:
        return self.supplier_completion_ms + self.visibility_delay_ms

    @property
    def retry_duration_ms(self) -> int:
        return self.retry_processing_ms or self.supplier_completion_ms

def immediate_blind_retry(s: Scenario) -> int:
    retry_sent = s.client_timeout_ms
    retry_completes = retry_sent + s.retry_duration_ms
    return 2 if retry_completes >= retry_sent else 1

def retrieve_before_retry(s: Scenario, attempts: int, delay_ms: int) -> tuple[int, int | None]:
    for i in range(attempts):
        retrieve_at = s.client_timeout_ms + i * delay_ms
        if retrieve_at >= s.first_visible_ms:
            return 1, retrieve_at
    retry_sent = s.client_timeout_ms + (attempts - 1) * delay_ms
    _retry_completes = retry_sent + s.retry_duration_ms
    return 2, None

def run() -> None:
    scenario = Scenario(supplier_completion_ms=700, client_timeout_ms=300, visibility_delay_ms=0)
    assert immediate_blind_retry(scenario) == 2
    orders, found_at = retrieve_before_retry(scenario, attempts=1, delay_ms=250)
    assert orders == 2 and found_at is None
    orders, found_at = retrieve_before_retry(scenario, attempts=3, delay_ms=250)
    assert orders == 1 and found_at == 800
    delayed_visibility = Scenario(supplier_completion_ms=500, client_timeout_ms=300, visibility_delay_ms=600)
    orders, found_at = retrieve_before_retry(delayed_visibility, attempts=3, delay_ms=250)
    assert orders == 2 and found_at is None
    orders, found_at = retrieve_before_retry(delayed_visibility, attempts=5, delay_ms=250)
    assert orders == 1 and found_at == 1300
    print("model-sanity: PASS")

if __name__ == "__main__":
    run()
