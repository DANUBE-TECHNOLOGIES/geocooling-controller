"use client";

import {
    useReducer,
    useRef,
    useEffect,
    useCallback
} from "react";

import {
    GeoCoolingContext,
    initialState
} from "../context/GeoCoolingContext";

import { reducer } from "../reducer/reducer";
import { normalizeSnapshot } from "../utils/normalizer";

const REFRESH_DELAY = 5000;

function errorMessage(error: unknown): string {
    if (error instanceof Error) {
        return error.message;
    }

    if (typeof error === "string") {
        return error;
    }

    return "Erreur GeoCooling inconnue";
}

export function GeoCoolingProvider({
    children,
}: {
    children: React.ReactNode;
}) {

    const [state, dispatch] = useReducer(
        reducer,
        initialState
    );

    const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

    const running = useRef(false);

    const refresh = useCallback(async () => {

        if (running.current) {
            return;
        }

        running.current = true;

        dispatch({
            type: "REFRESH"
        });

        const started = performance.now();

        try {

            const response = await fetch(
                "/api/geocooling/snapshot",
                {
                    cache: "no-store"
                }
            );

            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }

            const json = await response.json();

            dispatch({
                type: "SUCCESS",
                snapshot: normalizeSnapshot(json),
                duration: Math.round(
                    performance.now() - started
                )
            });

        } catch (error: unknown) {

            dispatch({
                type: "ERROR",
                error: errorMessage(error)
            });

        } finally {

            running.current = false;

            timer.current = setTimeout(
                refresh,
                REFRESH_DELAY
            );

        }

    }, []);

    useEffect(() => {

        dispatch({
            type: "LOADING"
        });

        refresh();

        return () => {

            if (timer.current) {

                clearTimeout(
                    timer.current
                );

            }

        };

    }, [refresh]);

    return (

        <GeoCoolingContext.Provider

            value={{

                state,

                refresh

            }}

        >

            {children}

        </GeoCoolingContext.Provider>

    );

}
