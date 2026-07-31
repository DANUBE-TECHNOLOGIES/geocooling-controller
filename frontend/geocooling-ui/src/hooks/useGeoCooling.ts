"use client";

import { useGeoCoolingStore } from "@/store/geocooling/hooks/useGeoCoolingStore";

export function useGeoCooling(){

    const {

        state,

        refresh

    }=useGeoCoolingStore();

    return{

        connected:state.connected,

        loading:state.loading,

        refreshing:state.refreshing,

        snapshot:state.snapshot,

        lastUpdate:state.lastUpdate,

        responseTime:state.responseTime,

        error:state.error,

        refresh

    };

}
