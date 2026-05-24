import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/context/auth-context";
import { TagSelectionProvider } from "@/context/tag-selection-context";
import AuthRoute from "@/components/auth-route";
import ProtectedRoute from "@/components/protected-route";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import Login from "./pages/auth/login";
import Signup from "./pages/auth/signup";
import ForgotPassword from "./pages/auth/forgot-password";
import Verified from "./pages/auth/verified";
import MfaVerify from "./pages/auth/mfa-verify";
import ForcePasswordSetup from "./pages/auth/ForcePasswordSetup";
import Admin from "./pages/admin/Admin";
import AdminRoute from "@/components/admin-route";
import IndustrialPrototype from "./pages/IndustrialPrototype";
import EnhancedHMI from "./pages/EnhancedHMI";
import DailyReport from "./pages/reports/DailyReport";
import ShiftReport from "./pages/reports/ShiftReport";
import MonthlyReport from "./pages/reports/MonthlyReport";


const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <AuthProvider>
          <TagSelectionProvider>
            <Routes>
              {/* Public Auth Routes */}
              <Route element={<AuthRoute />}>
                <Route path="/login" element={<Login />} />
                <Route path="/signup" element={<Signup />} />
                <Route path="/forgot-password" element={<ForgotPassword />} />
                <Route path="/verified" element={<Verified />} />
                <Route path="/mfa-verify" element={<MfaVerify />} />
                <Route path="/setup-password" element={<ForcePasswordSetup />} />
              </Route>

              {/* Protected Routes */}
              <Route element={<ProtectedRoute />}>
                <Route path="/" element={<IndustrialPrototype />} />
                <Route path="/dashboard" element={<Index />} />
                <Route path="/enhanced-hmi" element={<EnhancedHMI />} />
                <Route path="/reports/daily" element={<DailyReport />} />
                <Route path="/reports/shift" element={<ShiftReport />} />
                <Route path="/reports/monthly" element={<MonthlyReport />} />
              </Route>

              {/* Admin Routes */}
              <Route element={<AdminRoute />}>
                <Route path="/admin" element={<Admin />} />
              </Route>

              {/* Catch-all */}
              <Route path="*" element={<NotFound />} />
            </Routes>
          </TagSelectionProvider>
        </AuthProvider>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
