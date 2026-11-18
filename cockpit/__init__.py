"""TEL99 Agent Mission Control cockpit (issue #86).

Read-only presentation layer. It consumes already-proven data (issues
#77/#80/#84/#86, the versioned memory store and the OpenHands quota API) and
renders it for a mobile screen. It never talks to a model, never starts a
conversation, and never writes to the trading data or the public terminal.
"""
