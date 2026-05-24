import { LogOut, User, MapPin, ChevronDown, Check } from "lucide-react";
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
import { useMemo, useState, useEffect } from "react";
import api from "@/services/api";

interface PlantArea {
  id: number;
  plant: string;
  area: string;
  display_name: string;
}

const ACTIVE_AREA_KEY = "active_plant_area_id";

export const UserHeader = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [areas, setAreas] = useState<PlantArea[]>([]);
  const [activeAreaId, setActiveAreaId] = useState<string>(() =>
    localStorage.getItem(ACTIVE_AREA_KEY) || ""
  );

  const displayUser = useMemo(() => {
    if (user) return user;
    const stored = localStorage.getItem("auth_user");
    if (!stored) return null;
    try { return JSON.parse(stored); } catch { return null; }
  }, [user]);

  // Fetch the user's assigned areas once on mount
  useEffect(() => {
    if (!displayUser?.id) return;
    api.get(`/admin/users/${displayUser.id}/areas`)
      .then(res => {
        const assigned: PlantArea[] = (res.data.all_plants_areas || []).filter(
          (pa: any) => (res.data.assigned_plant_area_ids || []).includes(pa.id)
        );
        setAreas(assigned);
        // Auto-select first area if none stored
        if (!activeAreaId && assigned.length > 0) {
          const firstId = String(assigned[0].id);
          setActiveAreaId(firstId);
          localStorage.setItem(ACTIVE_AREA_KEY, firstId);
        }
      })
      .catch(() => {}); // non-critical — silently skip if endpoint unavailable
  }, [displayUser?.id]);

  const handleAreaChange = (id: string) => {
    setActiveAreaId(id);
    localStorage.setItem(ACTIVE_AREA_KEY, id);
    // Reload so all data queries pick up the new active area context
    window.location.reload();
  };

  const handleLogout = () => { logout(); navigate("/login"); };

  const getUserInitials = (username: string) =>
    username.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2);

  const activeArea = areas.find(a => String(a.id) === activeAreaId);
  const isAdmin = displayUser?.isAdmin;

  if (!displayUser) return null;

  return (
    <div className="flex items-center gap-2">
      {/* Area switcher — only shown for non-admin users with >1 area */}
      {!isAdmin && areas.length > 1 && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="h-9 gap-1.5 border-slate-700/50 bg-slate-800/50 hover:bg-slate-700/70 text-xs font-mono max-w-[180px]"
            >
              <MapPin className="h-3.5 w-3.5 text-amber-400 flex-shrink-0" />
              <span className="truncate">
                {activeArea ? activeArea.display_name : "Select Area"}
              </span>
              <ChevronDown className="h-3 w-3 text-slate-400 flex-shrink-0" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56 bg-slate-900 border-slate-700">
            <DropdownMenuLabel className="text-amber-400 text-xs font-bold flex items-center gap-1">
              <MapPin className="h-3.5 w-3.5" /> ACTIVE AREA
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-slate-700" />
            {areas.map(pa => (
              <DropdownMenuItem
                key={pa.id}
                onClick={() => handleAreaChange(String(pa.id))}
                className="text-xs text-slate-200 focus:bg-slate-700 focus:text-white cursor-pointer"
              >
                <Check className={`h-3.5 w-3.5 mr-2 flex-shrink-0 ${String(pa.id) === activeAreaId ? "text-amber-400" : "opacity-0"}`} />
                <div className="flex flex-col">
                  <span className="font-medium">{pa.area}</span>
                  <span className="text-[10px] text-slate-400">{pa.plant}</span>
                </div>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      {/* User profile dropdown */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            className="gap-2 h-9 px-3 border-slate-700/50 bg-slate-800/50 hover:bg-slate-700/70 hover:border-slate-600 transition-all"
          >
            <Avatar className="h-7 w-7 border-2 border-amber-500/50">
              <AvatarFallback className="bg-gradient-to-br from-amber-500 to-orange-600 text-white font-bold text-xs">
                {getUserInitials(displayUser.username)}
              </AvatarFallback>
            </Avatar>
            <div className="flex flex-col items-start">
              <span className="text-xs font-bold text-white uppercase tracking-wide leading-tight">{displayUser.username}</span>
              {displayUser.role && (
                <span className="text-[10px] text-amber-400 font-mono leading-tight">{displayUser.role.toUpperCase()}</span>
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
              <span className="font-bold text-white">{displayUser.username}</span>
            </div>
            {displayUser.role && (
              <span className="text-xs text-slate-400 ml-6 font-mono">
                ROLE: {displayUser.role.toUpperCase()}
              </span>
            )}
            {isAdmin && (
              <span className="text-xs text-violet-400 ml-6 font-bold">ADMINISTRATOR</span>
            )}
            {!isAdmin && activeArea && (
              <span className="text-xs text-amber-300 ml-6 font-mono flex items-center gap-1 mt-0.5">
                <MapPin className="h-3 w-3" />
                {activeArea.display_name}
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
    </div>
  );
};
