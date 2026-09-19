package io.github.blancaile.jevcontrol;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class DecisionLeaseTest {
    @Test void cancelledAndPreviousRunResponsesCannotAct() {
        var first = new DecisionLease();
        String old = first.begin(10);
        first.close();
        var second = new DecisionLease();
        String current = second.begin(12);
        assertThrows(IllegalStateException.class, () -> first.accept(old, 13, 20));
        assertThrows(IllegalStateException.class, () -> second.accept(old, 13, 20));
        second.accept(current, 13, 20);
        assertThrows(IllegalStateException.class, () -> second.accept(current, 13, 20));
    }
    @Test void concurrentRequestsAndStaleObservationsAreRejected() {
        var lease = new DecisionLease();
        String id = lease.begin(5);
        assertThrows(IllegalStateException.class, () -> lease.begin(6));
        assertThrows(IllegalStateException.class, () -> lease.accept(id, 4, 20));
        assertThrows(IllegalStateException.class, () -> lease.accept(id, 26, 20));
        lease.close();
        assertThrows(IllegalStateException.class, () -> lease.begin(30));
    }
}
