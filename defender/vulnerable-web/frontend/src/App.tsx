import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Navbar from "./components/Navbar";
import AdminDashboard from "./pages/AdminDashboard";
import BusinessCreate from "./pages/BusinessCreate";
import BusinessDetail from "./pages/BusinessDetail";
import Businesses from "./pages/Businesses";
import MyBusinesses from "./pages/MyBusinesses";
import Home from "./pages/Home";
import Login from "./pages/Login";
import UserProfile from "./pages/Profile";
import Register from "./pages/Register";
import Settings from "./pages/Settings";
import { AuthProvider, useAuth } from "./services/AuthContext";

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { user, loading } = useAuth();
  if (loading) return <div>Loading...</div>;
  return user ? <>{children}</> : <Navigate to="/login" replace />;
};

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="min-h-screen bg-background text-foreground">
          <Navbar />
          <main className="container mx-auto px-4 py-6">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route
                path="/settings"
                element={
                  <ProtectedRoute>
                    <Settings />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/admindashboard"
                element={
                  <ProtectedRoute>
                    <AdminDashboard />
                  </ProtectedRoute>
                }
              />
              <Route path="/businesses" element={<Businesses />} />
              <Route
                path="/my-businesses"
                element={
                  <ProtectedRoute>
                    <MyBusinesses />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/business/new"
                element={
                  <ProtectedRoute>
                    <BusinessCreate />
                  </ProtectedRoute>
                }
              />
              <Route path="/business/:id" element={<BusinessDetail />} />
              <Route path="/user/:username" element={<UserProfile />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </AuthProvider>
    </BrowserRouter>
  );
}
