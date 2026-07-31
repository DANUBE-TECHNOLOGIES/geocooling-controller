import type {
    BrainDecision,
    GeoCoolingMode
} from "@/types/geocooling";

export interface GeoCoolingSnapshot {

    available:boolean;

    generatedAt:string|null;

    indoorTemperature:number|null;

    humidity:number|null;

    sourceInTemperature:number|null;

    sourceOutTemperature:number|null;

    supplyTemperature:number|null;

    returnTemperature:number|null;

    pumpRunning:boolean;

    valveOpen:boolean;

    mode:GeoCoolingMode;

    safetySafe:boolean|null;

    deviceReady:boolean|null;

    decision:BrainDecision;

}

export interface GeoCoolingState{

    connected:boolean;

    loading:boolean;

    refreshing:boolean;

    lastUpdate:Date|null;

    responseTime:number;

    snapshot:GeoCoolingSnapshot|null;

    error:string|null;

}
