import { Route, Routes } from 'react-router-dom'
import { Toaster } from '@/components/Toaster'
import Library from '@/pages/Library'
import TrajectoryPage from '@/pages/Trajectory'

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<Library />} />
        <Route path="/t/:id" element={<TrajectoryPage />} />
        <Route path="*" element={<Library />} />
      </Routes>
      <Toaster />
    </>
  )
}
