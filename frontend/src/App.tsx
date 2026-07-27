import { Navigate, Route, Routes } from 'react-router-dom';

import { AppHeader } from './components/AppHeader';
import { ComplaintDetailPage } from './pages/ComplaintDetailPage';
import { ComplaintsPage } from './pages/ComplaintsPage';
import { IntakePage } from './pages/IntakePage';

export default function App() {
  return (
    <>
      <AppHeader />
      <main>
        <Routes>
          <Route path="/" element={<IntakePage />} />
          <Route path="/complaints" element={<ComplaintsPage />} />
          <Route path="/complaints/:complaintId" element={<ComplaintDetailPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}
