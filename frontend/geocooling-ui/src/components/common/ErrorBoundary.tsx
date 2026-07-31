"use client";

import React from "react";

export class ErrorBoundary extends React.Component<

{

children:React.ReactNode

},

{

error:boolean

}

>{

constructor(props:any){

super(props);

this.state={

error:false

};

}

static getDerivedStateFromError(){

return{

error:true

};

}

componentDidCatch(error:any){

console.error(

"Dashboard Error",

error

);

}

render(){

if(this.state.error){

return(

<div className="gc-error">

<h2>

Erreur Dashboard

</h2>

<p>

Un composant a rencontré une erreur.

</p>

</div>

);

}

return this.props.children;

}

}
