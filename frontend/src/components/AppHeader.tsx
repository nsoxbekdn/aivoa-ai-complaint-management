import { NavLink } from 'react-router-dom';

export function AppHeader() {
  return (
    <header className="app-header">
      <div className="app-header__inner">
        <div className="app-header__brand">
          <div className="app-header__logo" aria-hidden="true">
            AV
          </div>
          <div>
            <div className="app-header__title">AIVOA · Customer Complaint Management</div>
            <div className="app-header__subtitle">
              Pharmaceutical quality intake · AI-assisted, human-approved
            </div>
          </div>
        </div>
        <nav className="app-nav">
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'is-active' : '')}>
            Log complaint
          </NavLink>
          <NavLink to="/complaints" className={({ isActive }) => (isActive ? 'is-active' : '')}>
            Complaints
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
