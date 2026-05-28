import { useState, useEffect, useRef } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/auth-context";
import { Button } from "@/components/ui/button";
import {
    Form,
    FormControl,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

const formSchema = z.object({
    username: z.string().min(1, "Username is required"),
    password: z.string().min(1, "Password is required"),
});

const Login = () => {
    // Random field names generated on every mount — defeats Chrome autofill matching
    const fieldId = useRef(`f_${Math.random().toString(36).slice(2)}`);
    const { login } = useAuth();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const [loading, setLoading] = useState(false);

    // Check for session expiration message
    useEffect(() => {
        const sessionExpired = searchParams.get('session_expired');
        const reason = searchParams.get('reason');

        if (sessionExpired === 'true') {
            toast.error("Your session has been terminated. Please login again.", {
                duration: 5000,
            });
            navigate('/login', { replace: true });
        } else if (reason === 'superseded') {
            toast.warning("You were logged in from another device. This session has been ended.", {
                duration: 6000,
            });
            navigate('/login', { replace: true });
        }
    }, [searchParams, navigate]);

    const form = useForm<z.infer<typeof formSchema>>({
        resolver: zodResolver(formSchema),
        defaultValues: {
            username: "",
            password: "",
        },
    });

    async function onSubmit(values: z.infer<typeof formSchema>) {
        setLoading(true);
        try {
            const result = await login(values.username, values.password);
            if (result.success) {
                toast.success("Login successful");
                navigate("/");
            } else if (result.mustChangePassword) {
                toast.info("Please set up your new password.");
                navigate("/setup-password");
            } else if (result.mfaRequired) {
                // Handle MFA flow - maybe navigate to an MFA page or show a modal
                // For now let's assume direct login or we need to handle MFA in the context/ui
                // Implementation plan didn't explicitly ask for a separate MFA page but verifyMfa is in context.
                // We might need to add MFA handling here or in a separate step.
                // Given the request "Create a login page... register screen... forgot password", MFA wasn't explicitly detailed in the "user request" prompt text but was in the context.
                // I will add a TO-DO or basic handling.
                toast.info("MFA required - Please verify your identity");
                navigate("/mfa-verify");
                // We'll implementation MFA verification modal or page if needed.
                // For now, let's just show a toast.
            }
        } catch (error: any) {
            toast.error(error.message || "Login failed");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="flex min-h-screen items-center justify-center bg-background p-4">
            <Card className="w-full max-w-md">
                <CardHeader className="space-y-1">
                    <CardTitle className="text-2xl font-bold">Login</CardTitle>
                    <CardDescription>
                        Enter your credentials to access your account
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Form {...form}>
                        {/* Hide search-input clear button (×) that Chrome renders on type=search */}
                        <style>{`input[type=search]::-webkit-search-cancel-button,input[type=search]::-webkit-search-decoration{display:none}`}</style>
                        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" autoComplete="off">
                            <FormField
                                control={form.control}
                                name="username"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>Username</FormLabel>
                                        <FormControl>
                                            {/*
                                              type="search" is the ONLY input type Chrome
                                              categorically never autofills with saved contacts.
                                              Random name/id on every mount defeats any fallback matching.
                                            */}
                                            <Input
                                                type="search"
                                                placeholder="Enter your username"
                                                autoComplete="off"
                                                name={fieldId.current + '_u'}
                                                id={fieldId.current + '_u'}
                                                data-lpignore="true"
                                                data-form-type="other"
                                                value={field.value}
                                                onChange={field.onChange}
                                                onBlur={field.onBlur}
                                                ref={field.ref}
                                            />
                                        </FormControl>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />
                            <FormField
                                control={form.control}
                                name="password"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>Password</FormLabel>
                                        <FormControl>
                                            <Input
                                                type="password"
                                                placeholder="Enter your password"
                                                autoComplete="new-password"
                                                name={fieldId.current + '_p'}
                                                id={fieldId.current + '_p'}
                                                data-lpignore="true"
                                                data-form-type="other"
                                                value={field.value}
                                                onChange={field.onChange}
                                                onBlur={field.onBlur}
                                                ref={field.ref}
                                            />
                                        </FormControl>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />
                            <Button type="submit" className="w-full" disabled={loading}>
                                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                Sign In
                            </Button>
                        </form>
                    </Form>
                </CardContent>
                <CardFooter className="flex flex-col gap-2 text-center text-sm">
                    <Link to="/forgot-password" className="text-primary hover:underline">
                        Forgot password?
                    </Link>
                    <div className="text-muted-foreground">
                        Don't have an account?{" "}
                        <Link to="/signup" className="text-primary hover:underline">
                            Sign up
                        </Link>
                    </div>
                </CardFooter>
            </Card>
        </div>
    );
};

export default Login;
