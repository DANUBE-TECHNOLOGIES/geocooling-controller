import {createContext} from "react";
import type {GeoCoolingState} from "../types/state";

export interface GeoCoolingContextType {

  state: GeoCoolingState;

  refresh:()=>Promise<void>;

}

export const initialState:GeoCoolingState={

  connected:false,

  loading:true,

  refreshing:false,

  lastUpdate:null,

  responseTime:0,

  snapshot:null,

  error:null

};

export const GeoCoolingContext=createContext<GeoCoolingContextType>({

    state:initialState,

    refresh:async()=>{}

});
