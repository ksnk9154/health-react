import { Navigate } from 'react-router';
import { useAuth } from '../contexts/AuthContext';

// ProtectedRoute optionally enforces a role requirement on top of authentication.
// requiredRole may be a single role string (e.g. "Admin") or an array (e.g. ["Admin", "Staff"]).
// Role comparison is case-insensitive to match both "Admin" (backend) and "admin" (frontend) spellings.
const ProtectedRoute = ({ children, requiredRole }) => {
  const { user, isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-600 dark:text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Optional role-based access control
  if (requiredRole) {
    const allowed = Array.isArray(requiredRole) ? requiredRole : [requiredRole];
    const userRole = (user?.role || '').toLowerCase();
    const hasRole = allowed.some((role) => role.toLowerCase() === userRole);
    if (!hasRole) {
      return <Navigate to="/home" replace />;
    }
  }

  return children;
};

export default ProtectedRoute;
