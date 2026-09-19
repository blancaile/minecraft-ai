package io.github.blancaile.jevcontrol;

public enum ControlAction {
    WAIT("Release all controls for the bounded interval"),
    FORWARD("Walk forward relative to current yaw"),
    BACK("Walk backward relative to current yaw"),
    STRAFE_LEFT("Walk left without changing yaw"),
    STRAFE_RIGHT("Walk right without changing yaw"),
    TURN_LEFT("Turn yaw left by 15 degrees, with no translation input"),
    TURN_RIGHT("Turn yaw right by 15 degrees, with no translation input"),
    JUMP_FORWARD("Jump once while grounded and walk forward for the bounded interval");

    public final String description;
    ControlAction(String description) { this.description = description; }
}
