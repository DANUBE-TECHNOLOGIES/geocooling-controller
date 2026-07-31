import type {
    GeoCoolingMode,
    GeoCoolingSnapshot
} from "@/types/geocooling";

function normalizeMode(value: unknown): GeoCoolingMode {

    switch (String(value).toLowerCase()) {

        case "manual":
            return "manual";

        case "automatic":
            return "automatic";

        case "simulation":
            return "simulation";

        default:
            return "unknown";
    }

}

export function normalizeSnapshot(raw: any): GeoCoolingSnapshot {

    return {

        available: Boolean(raw?.available),

        generatedAt:
            raw?.generatedAt ??
            null,

        indoorTemperature:
            raw?.indoorTemperature ??
            null,

        humidity:
            raw?.humidity ??
            null,

        sourceInTemperature:
            raw?.sourceInTemperature ??
            null,

        sourceOutTemperature:
            raw?.sourceOutTemperature ??
            null,

        supplyTemperature:
            raw?.supplyTemperature ??
            null,

        returnTemperature:
            raw?.returnTemperature ??
            null,

        pumpRunning:
            Boolean(raw?.pumpRunning),

        valveOpen:
            Boolean(raw?.valveOpen),

        mode:
            normalizeMode(raw?.mode),

        safetySafe:
            raw?.safetySafe ??
            null,

        deviceReady:
            raw?.deviceReady ??
            null,

        decision:
            raw?.decision ?? {

                summary: "",

                confidence: 0,

                reasons: []

            }

    };

}
