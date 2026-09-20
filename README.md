# Airline Booking Retry Research

Experimental platform for the paper:

> **Evaluating Retrieve-Before-Retry Reconciliation for Ambiguous Airline Booking Timeouts**

This repository compares immediate blind retry, delayed blind retry, single retrieve-before-retry, and bounded retrieve-before-retry reconciliation for ambiguous airline booking outcomes.

## Core rule

A supplier retrieve timeout or transient failure does not prove that the booking is absent. A new OrderCreate is permitted only after the configured reconciliation policy receives explicit NOT_FOUND outcomes.

The complete scaffold includes a .NET 10 booking strategy service, deterministic supplier simulator, PostgreSQL ground-truth schema, k6 workloads, Docker Compose, analysis SQL, smoke tests, and GitHub Actions CI.
