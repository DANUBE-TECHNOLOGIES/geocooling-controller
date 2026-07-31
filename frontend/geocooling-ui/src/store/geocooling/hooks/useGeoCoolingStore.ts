"use client";

import {useContext} from "react";

import {GeoCoolingContext}
from "../context/GeoCoolingContext";

export function useGeoCoolingStore(){

return useContext(GeoCoolingContext);

}
