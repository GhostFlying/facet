"""Bounded serial retries for reconcile reads only, never target inserts."""

import random
import time

from facet.contracts import ErrorCode, Role
from facet.gmail.retry import ProviderFailure, ProviderReason

MAX_RETRIES = 8
WAIT_BUDGET_SECONDS = 1800


def retryable(error):
    return isinstance(error, ProviderFailure) and (
        error.status == 429
        or error.status == 403
        and error.reason in {ProviderReason.RATE_LIMIT, ProviderReason.USER_RATE_LIMIT}
        or error.status in {500, 502, 503, 504}
        or error.status is None
        and error.code is ErrorCode.NETWORK_UNAVAILABLE
    )


class ReadRetries:
    def __init__(
        self,
        guard,
        *,
        sleep=time.sleep,
        clock=time.monotonic,
        jitter=random.random,
        notify=None,
    ):
        self.guard = guard
        self.sleep = sleep
        self.clock = clock
        self.jitter = jitter
        self.notify = notify
        self.waited = 0.0
        self.retried_success = 0

    def wait(self, errors, retry):
        if retry > MAX_RETRIES:
            return False
        delay = min(2 ** (retry - 1), 60) * (1 + 0.25 * self.jitter())
        delay = max(delay, max((e.retry_after_seconds or 0 for e in errors), default=0))
        if delay > WAIT_BUDGET_SECONDS - self.waited:
            return False
        self.guard()
        if self.notify:
            self.notify(errors, retry, delay, WAIT_BUDGET_SECONDS - self.waited)
        start = self.clock()
        deadline = start + delay
        while self.clock() < deadline:
            self.sleep(min(1, deadline - self.clock()))
        self.waited += max(delay, self.clock() - start)
        self.guard()
        return True

    def call(self, read):
        for retry in range(MAX_RETRIES + 1):
            self.guard()
            try:
                result = read()
                self.retried_success += retry > 0
                return result
            except ProviderFailure as error:
                if not retryable(error) or not self.wait((error,), retry + 1):
                    raise

    def batch(self, items, read):
        pending = items
        results = {}
        for retry in range(MAX_RETRIES + 1):
            self.guard()
            try:
                current = read(pending)
            except ProviderFailure as error:
                current = {item.message_id.value: error for item in pending}
            unresolved = []
            errors = []
            for item in pending:
                value = current.get(item.message_id.value)
                if value is None:
                    value = ProviderFailure(ErrorCode.CONSISTENCY_FAILURE, Role.SOURCE)
                results[item.message_id.value] = value
                if retryable(value):
                    unresolved.append(item)
                    errors.append(value)
                elif retry and not isinstance(value, ProviderFailure):
                    self.retried_success += 1
            if not unresolved or not self.wait(errors, retry + 1):
                return results
            pending = tuple(unresolved)
        return results
