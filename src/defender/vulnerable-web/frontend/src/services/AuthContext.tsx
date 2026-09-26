import { setLogoutHandler } from "@/lib/auth";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type Context,
} from "react";
import { useNavigate } from "react-router-dom";
import axiosInstance from "./axios";
import { SessionService } from "./session";

export type User = {
  id: number;
  username: string;
  email: string;
  first_name?: string;
  last_name?: string;
  isBusinessOwner?: boolean;
  role: string;
};

type AuthContextType = {
  isAuthenticated: boolean;
  user: User | null;
  loading: boolean;
  login: (accessToken: string, refreshToken: string, username: string) => void;
  logout: () => void;
  fetchUserData: () => Promise<void>;
};

const AuthContext: Context<AuthContextType> = createContext(
  {} as AuthContextType
);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const fetchUserData = async () => {
    try {
      const username = SessionService.getUserName();
      if (!username) {
        setUser(null);
        return;
      }

      // Fetch fresh user from API
      const res = await axiosInstance.get(`users/username/${username}/`);
      const data = Array.isArray(res.data) ? res.data[0] : res.data;

      if (data) {
        setUser(data);
        SessionService.setUserData(data);
      } else {
        setUser(null);
        SessionService.removeUserData();
      }
    } catch (err) {
      console.error("Error fetching user data:", err);
      setUser(null);
      SessionService.removeUserData();
    }
  };

  useEffect(() => {
    const init = async () => {
      const token = SessionService.getAccessToken();
      if (token) {
        setIsAuthenticated(true);
        await fetchUserData();
      } else {
        setIsAuthenticated(false);
      }
      setLoading(false);
    };
    init();
  }, []);

  const login = (
    accessToken: string,
    refreshToken: string,
    username: string
  ) => {
    SessionService.setAccessToken(accessToken);
    SessionService.setRefreshToken(refreshToken);
    SessionService.setUserName(username);
    setIsAuthenticated(true);
    fetchUserData();
  };

  const logout = () => {
    SessionService.clear();

    setIsAuthenticated(false);
    setUser(null);
    navigate("/");
  };

  useEffect(() => {
    setLogoutHandler(logout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        user,
        loading,
        login,
        logout,
        fetchUserData,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext<AuthContextType>(AuthContext);
