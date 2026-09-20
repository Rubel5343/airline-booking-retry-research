import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';

const totalRequests = Number(__ENV.TOTAL_REQUESTS || 500);
const vus = Number(__ENV.VUS || 20);

export const options = {
  scenarios: {
    correctness: {
      executor: 'shared-iterations',
      vus,
      iterations: totalRequests,
      maxDuration: __ENV.MAX_DURATION || '10m',
    },
  },
};

const baseUrl = __ENV.BOOKING_URL || 'http://localhost:8080';
const runId = __ENV.RUN_ID;
const strategy = __ENV.STRATEGY || 'RetrieveBeforeRetry';
const faultCohort = __ENV.FAULT_COHORT || runId;

if (!runId) {
  throw new Error('RUN_ID environment variable is required');
}

export default function () {
  const sequence = exec.scenario.iterationInTest;
  const id = `${faultCohort}-${sequence}`;

  const payload = JSON.stringify({
    experimentRunId: runId,
    logicalBookingId: `BKG-${id}`,
    clientReference: `EXP-${id}`,
    origin: 'DAC',
    destination: 'LHR',
    strategy,
    faultCohort,
    bookingTimeoutMs: Number(__ENV.BOOKING_TIMEOUT_MS || 300),
    delayedRetryMs: Number(__ENV.DELAYED_RETRY_MS || 250),
    retrieveAttempts: Number(__ENV.RETRIEVE_ATTEMPTS || 3),
    retrieveDelayMs: Number(__ENV.RETRIEVE_DELAY_MS || 250),
  });

  const response = http.post(`${baseUrl}/bookings`, payload, {
    headers: { 'Content-Type': 'application/json' },
  });

  check(response, {
    'booking endpoint returned handled state': (r) => [200, 202].includes(r.status),
  });
}
