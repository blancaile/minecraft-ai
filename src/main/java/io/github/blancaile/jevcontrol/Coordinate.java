package io.github.blancaile.jevcontrol;

final class Coordinate {
    static double parse(String token, double origin) {
        boolean relative = token.startsWith("~");
        String number = relative ? token.substring(1) : token;
        double value = (relative ? origin : 0) + (relative && number.isEmpty() ? 0 : Double.parseDouble(number));
        if (!Double.isFinite(value)) throw new IllegalArgumentException("Coordinates must be finite");
        return value;
    }
}
