package io.github.blancaile.jevcontrol;

import java.util.UUID;

/** Binds a single decision to one run and snapshot; cancelled leases can never be reused. */
public final class DecisionLease {
    private final String runId = UUID.randomUUID().toString();
    private String pending;
    private long observedTick;
    private boolean closed;

    public String runId() { return runId; }
    public String begin(long tick) {
        if (closed || pending != null) throw new IllegalStateException("Decision already pending or run closed");
        observedTick = tick;
        pending = UUID.randomUUID().toString();
        return pending;
    }
    public void accept(String id, long tick, int maxAge) {
        if (closed || pending == null || !pending.equals(id)) throw new IllegalStateException("Invalid decision lease");
        if (tick < observedTick || tick - observedTick > maxAge) throw new IllegalStateException("Stale observation");
        pending = null;
    }
    public void close() { closed = true; pending = null; }
}
