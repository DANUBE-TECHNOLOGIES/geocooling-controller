"use client";

import {
  createContext,
  useContext,
  useMemo,
  useState,
} from "react";

import type { GeoCoolingSnapshot } from "@/types/geocooling";

type ContextType = {
  enabled: boolean;
  setEnabled: (value:boolean)=>void;

  simulatedSnapshot: GeoCoolingSnapshot | null;
  setSimulatedSnapshot:(value:GeoCoolingSnapshot|null)=>void;
};

const SimulationContext =
createContext<ContextType | null>(null);

export function SimulationProvider({
  children,
}:{
  children:React.ReactNode;
}){

  const [enabled,setEnabled]=useState(false);

  const [
    simulatedSnapshot,
    setSimulatedSnapshot
  ]=useState<GeoCoolingSnapshot|null>(null);

  const value=useMemo(()=>({

    enabled,
    setEnabled,

    simulatedSnapshot,
    setSimulatedSnapshot

  }),[
    enabled,
    simulatedSnapshot
  ]);

  return(

    <SimulationContext.Provider value={value}>

      {children}

    </SimulationContext.Provider>

  );

}

export function useSimulation(){

  const ctx=useContext(
    SimulationContext
  );

  if(!ctx){

    throw new Error(
      "SimulationProvider manquant"
    );

  }

  return ctx;

}
