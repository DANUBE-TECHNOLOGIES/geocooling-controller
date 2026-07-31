import "./globals.css";

import { GeoCoolingProvider } from "@/store/geocooling/provider/GeoCoolingProvider";

import { ErrorBoundary } from "@/components/common/ErrorBoundary";

export const metadata = {
    title: "GeoCooling Controller",
    description: "Enterprise Dashboard"
};

export default function RootLayout({
    children,
}:{
    children:React.ReactNode;
}){

    return(

<html lang="fr">

<body>

<GeoCoolingProvider>

<ErrorBoundary>

{children}

</ErrorBoundary>

</GeoCoolingProvider>

</body>

</html>

    );

}
