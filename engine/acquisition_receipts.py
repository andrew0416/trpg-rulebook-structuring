"""Compatibility entry points for the actor's native acquisition ledger."""
from acquisition_ledger import AcquisitionLedger


def read(engine, actor):
    return AcquisitionLedger(actor).read(engine)


def account(engine, actor):
    return AcquisitionLedger(actor).account(engine)
