import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/services/AuthContext";
import { useTheme } from "@/services/ThemeProvider";
import { ChevronDown, LogOut, Moon, Settings, Sun, User } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Button } from "./ui/button";

export default function Navbar() {
  const { isAuthenticated, logout, user } = useAuth();
  const { theme, setTheme } = useTheme();
  const nav = useNavigate();
  const { pathname } = useLocation();

  const onLogout = () => {
    logout();
    nav("/login");
  };

  const linkCls = (path: string) =>
    `px-3 py-2 rounded-md text-sm font-medium ${
      pathname === path
        ? "bg-primary text-primary-foreground"
        : "hover:bg-muted"
    }`;

  return (
    <header className="border-b bg-card">
      <div className="container mx-auto flex items-center gap-4 px-4 py-3">
        <Link to="/" className="text-xl font-semibold">
          SecureReview
        </Link>

        <nav className="flex gap-2">
          <Link className={linkCls("/")} to="/">
            Home
          </Link>
          <Link className={linkCls("/businesses")} to="/businesses">
            Businesses
          </Link>
          {isAuthenticated && (
            <>
              {user?.role === "business_owner" && (
                <>
                  <Link className={linkCls("/business/new")} to="/business/new">
                    New Business
                  </Link>
                  <Link
                    className={linkCls("/my-businesses")}
                    to="/my-businesses"
                  >
                    My Businesses
                  </Link>
                </>
              )}
              {user?.role === "admin" && (
                <Link
                  className={linkCls("/admindashboard")}
                  to="/admindashboard"
                >
                  Dashboard
                </Link>
              )}
            </>
          )}
        </nav>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Toggle theme"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          {theme === "dark" ? (
            <Sun className="h-5 w-5" />
          ) : (
            <Moon className="h-5 w-5" />
          )}
        </Button>

        <div className="ml-auto flex items-center gap-2">
          {isAuthenticated && user ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="flex items-center gap-1">
                  {user.username}
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem
                  onClick={() => nav(`/user/${user.username}`)}
                  className="cursor-pointer"
                >
                  <User className="mr-2 h-4 w-4" />
                  <span>Profile</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => nav("/settings")}
                  className="cursor-pointer"
                >
                  <Settings className="mr-2 h-4 w-4" />
                  <span>Settings</span>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={onLogout}
                  className="cursor-pointer text-red-600 focus:text-red-600"
                >
                  <LogOut className="mr-2 h-4 w-4" />
                  <span>Log out</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <Link to="/login">
              <Button>Login</Button>
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
