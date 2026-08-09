import type {
    GeoCoolingSnapshot
} from "@/types/geocooling";

export interface GeoCoolingState{

    connected:boolean;

    loading:boolean;

    refreshing:boolean;

    lastUpdate:Date|null;

    responseTime:number;

    snapshot:GeoCoolingSnapshot|null;

    error:string|null;

}
