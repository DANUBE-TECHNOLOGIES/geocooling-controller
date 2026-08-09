import type {
    GeoCoolingState
} from "../types/state";
import type {
    GeoCoolingSnapshot
} from "@/types/geocooling";

export type Action=

|{type:"LOADING"}

|{type:"REFRESH"}

|{

    type:"SUCCESS";

    snapshot:GeoCoolingSnapshot;

    duration:number;

}

|{

    type:"ERROR";

    error:string;

};

export function reducer(

state:GeoCoolingState,

action:Action

):GeoCoolingState{

switch(action.type){

case"LOADING":

return{

...state,

loading:true

};

case"REFRESH":

return{

...state,

refreshing:true

};

case"SUCCESS":

return{

...state,

loading:false,

refreshing:false,

connected:true,

snapshot:action.snapshot,

lastUpdate:new Date(),

responseTime:action.duration,

error:null

};

case"ERROR":

return{

...state,

loading:false,

refreshing:false,

connected:false,

error:action.error

};

default:

return state;

}

}
