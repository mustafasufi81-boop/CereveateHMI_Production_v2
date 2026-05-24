import { useState, useEffect, useCallback } from "react";
import api from "@/services/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertCircle, RefreshCw, Unlock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { format } from "date-fns";
import { useToast } from "@/hooks/use-toast";

const AlertsTab = () => {
    const [alerts, setAlerts] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const { toast } = useToast();

    const fetchAlerts = useCallback(async () => {
        setLoading(true);
        try {
            const response = await api.get('/admin/alerts');
            setAlerts(response.data.alerts || []);
        } catch (error) {
            console.error("Failed to fetch alerts", error);
        } finally {
            setLoading(false);
        }
    }, []);

    const unlockUser = async (userId: number) => {
        if (!confirm('Are you sure you want to unlock this user account?')) return;
        
        try {
            await api.post(`/admin/users/${userId}/unlock`);
            toast({
                title: "Success",
                description: "User account unlocked successfully",
            });
            fetchAlerts();
        } catch (error: any) {
            toast({
                title: "Error",
                description: error.response?.data?.message || "Failed to unlock user",
                variant: "destructive",
            });
        }
    };

    useEffect(() => {
        fetchAlerts();
    }, [fetchAlerts]);

    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center">
                <h3 className="text-lg font-medium">System Alerts</h3>
                <Button variant="outline" size="sm" onClick={fetchAlerts} disabled={loading}>
                    <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                    Refresh
                </Button>
            </div>

            <div className="grid gap-4">
                {alerts.map((alert) => {
                    const userIdValue = alert.userId || alert.user_id;
                    return (
                    <Card key={alert.id} className="border-l-4 border-l-destructive/50">
                        <CardContent className="p-4 flex gap-4 items-start">
                            <div className="bg-destructive/10 p-2 rounded-full text-destructive shrink-0">
                                <AlertCircle className="h-5 w-5" />
                            </div>
                            <div className="flex-1 space-y-1">
                                <div className="flex items-center justify-between">
                                    <Badge variant="outline" className="border-destructive/30 text-destructive font-bold uppercase text-[10px] tracking-wider">
                                        {alert.type}
                                    </Badge>
                                    <span className="text-xs text-muted-foreground">
                                        {format(new Date(alert.createdAt), 'PPpp')}
                                    </span>
                                </div>
                                <p className="text-sm font-medium leading-normal">
                                    {alert.message}
                                </p>
                                {alert.username && (
                                    <div className="flex items-center gap-2 mt-2">
                                        <div className="h-5 w-5 rounded-full bg-secondary flex items-center justify-center text-[10px]">
                                            {alert.username[0].toUpperCase()}
                                        </div>
                                        <span className="text-xs text-muted-foreground">{alert.username}</span>
                                        {alert.lockoutUntil && (
                                            <Badge variant={new Date(alert.lockoutUntil) > new Date() ? "destructive" : "secondary"} className="text-[10px]">
                                                {new Date(alert.lockoutUntil) > new Date() ? '🔒 Locked' : '✓ Expired'}
                                            </Badge>
                                        )}
                                    </div>
                                )}
                            </div>
                            {alert.type === 'ACCOUNT_LOCKOUT' && userIdValue && alert.lockoutUntil && new Date(alert.lockoutUntil) > new Date() && (
                                <Button 
                                    size="sm" 
                                    variant="outline" 
                                    className="border-green-600/30 text-green-600 hover:bg-green-600/10 shrink-0"
                                    onClick={() => unlockUser(userIdValue)}
                                >
                                    <Unlock className="h-4 w-4 mr-1.5" />
                                    Unlock Account
                                </Button>
                            )}
                        </CardContent>
                    </Card>
                    );
                })}

                {alerts.length === 0 && !loading && (
                    <div className="text-center py-12 text-muted-foreground border-2 border-dashed rounded-lg">
                        No system alerts found
                    </div>
                )}
            </div>
        </div>
    );
};

export default AlertsTab;
