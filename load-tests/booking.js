import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';

export const options = {
  scenarios: {
    bookings: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 10),
      timeUnit: '1s',
      duration: __ENV.DURATION || '2m',
      preAllocatedVUs: Number(__ENV.PRE_VUS || 50),
      maxVUs: Number(__ENV.MAX_VUS || 500),
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
  const id = `${faultCohort}-${exec.scenario.iterationInTest}`;
  const payload = JSON.stringify({
    experimentRunId: runId,
    logicalBookingId: `BKG-${id}`,
    clientReference: `EXP-${id}`,
    origin: 'DAC',
    destination: 'LHR',
    strategy,
    faultCohort,
    bookingTimeoutMs: Number(__ENV.BOOKING_TIMEOUT_MS || 3000),
    delayedRetryMs: Number(__ENV.DELAYED_RETRY_MS || 1000),
    retrieveAttempts: Number(__ENV.RETRIEVE_ATTEMPTS || 3),
    retrieveDelayMs: Number(__ENV.RETRIEVE_DELAY_MS || 1000),
  });

  const response = http.post(`${baseUrl}/bookings`, payload, {
    headers: { 'Content-Type': 'application/json' },
  });

  check(response, {
    'booking endpoint returned handled state': (r) => [200, 202].includes(r.status),
  });
}
