import { LogOut, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useAuth } from "@/context/auth-context";
import { useNavigate } from "react-router-dom";

export const UserHeader = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const getUserInitials = (username: string) => {
    return username
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  };

  if (!user) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button 
          variant="outline" 
          className="gap-2 h-9 px-3 border-slate-700/50 bg-slate-800/50 hover:bg-slate-700/70 hover:border-slate-600 transition-all"
        >
          <Avatar className="h-7 w-7 border-2 border-amber-500/50">
            <AvatarFallback className="bg-gradient-to-br from-amber-500 to-orange-600 text-white font-bold text-xs">
              {getUserInitials(user.username)}
            </AvatarFallback>
          </Avatar>
          <div className="flex flex-col items-start">
            <span className="text-xs font-bold text-white uppercase tracking-wide leading-tight">{user.username}</span>
            {user.role && (
              <span className="text-[10px] text-amber-400 font-mono leading-tight">{user.role.toUpperCase()}</span>
            )}
          </div>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56 bg-slate-900 border-slate-700">
        <DropdownMenuLabel className="text-amber-400 font-bold">OPERATOR PROFILE</DropdownMenuLabel>
        <DropdownMenuSeparator className="bg-slate-700" />
        <DropdownMenuItem disabled className="flex items-start flex-col py-2">
          <div className="flex items-center gap-2 mb-1">
            <User className="h-4 w-4 text-amber-400" />
            <span className="font-bold text-white">{user.username}</span>
          </div>
          {user.role && (
            <span className="text-xs text-slate-400 ml-6 font-mono">
              ROLE: {user.role.toUpperCase()}
            </span>
          )}
          {user.isAdmin && (
            <span className="text-xs text-violet-400 ml-6 font-bold">
              ADMINISTRATOR
            </span>
          )}
        </DropdownMenuItem>
        <DropdownMenuSeparator className="bg-slate-700" />
        <DropdownMenuItem
          onClick={handleLogout}
          className="text-red-400 font-bold focus:text-red-300 focus:bg-red-900/30 cursor-pointer"
        >
          <LogOut className="h-4 w-4 mr-2" />
          SIGN OUT
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
