const nav = [["▦","Accueil"],["◇","Twin"],["⌁","Courbes"],["⚙","État"],["≡","Réglages"]];

export function MobileNav() {
  return (
    <nav className="mobile-nav">
      {nav.map(([icon, label]) => (
        <a href="#" key={label}><span>{icon}</span>{label}</a>
      ))}
    </nav>
  );
}
