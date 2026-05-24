import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Link, useNavigate } from "react-router-dom";
import { authService } from "@/services/auth-service";
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
import { Loader2, ArrowLeft, ShieldQuestion, KeyRound } from "lucide-react";

// Step 1 schema
const usernameSchema = z.object({
    username: z.string().min(1, "Username is required"),
});

// Step 3 schema
const resetSchema = z.object({
    answer: z.string().min(1, "Answer/Key is required"),
    newPassword: z.string().min(6, "Password must be at least 6 characters"),
    confirmPassword: z.string(),
}).refine((data) => data.newPassword === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
});

const ForgotPassword = () => {
    const navigate = useNavigate();
    const [step, setStep] = useState(1);
    const [username, setUsername] = useState("");
    const [questionData, setQuestionData] = useState<{ index: number; text: string } | null>(null);
    const [method, setMethod] = useState<"question" | "key" | null>(null);
    const [loading, setLoading] = useState(false);

    const usernameForm = useForm<z.infer<typeof usernameSchema>>({
        resolver: zodResolver(usernameSchema),
        defaultValues: { username: "" },
    });

    const resetForm = useForm<z.infer<typeof resetSchema>>({
        resolver: zodResolver(resetSchema),
        defaultValues: { answer: "", newPassword: "", confirmPassword: "" },
    });

    async function onCheckUser(values: z.infer<typeof usernameSchema>) {
        setLoading(true);
        try {
            const result = await authService.checkResetUser(values.username);
            if (result.found) {
                setUsername(values.username);
                if (result.question) {
                    setQuestionData(result.question);
                }
                setStep(2);
            } else {
                toast.error("User not found");
            }
        } catch (error: any) {
            toast.error(error.message || "Failed to check user");
        } finally {
            setLoading(false);
        }
    }

    async function onReset(values: z.infer<typeof resetSchema>) {
        if (!method) return;
        setLoading(true);
        try {
            await authService.resetPassword({
                username,
                method,
                answer: values.answer,
                newPassword: values.newPassword,
                questionIndex: method === "question" ? questionData?.index : undefined
            });
            toast.success("Password reset successful");
            navigate("/login");
        } catch (error: any) {
            toast.error(error.message || "Password reset failed");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="flex min-h-screen items-center justify-center bg-background p-4">
            <Card className="w-full max-w-md">
                <CardHeader className="space-y-1">
                    <CardTitle className="text-2xl font-bold">Reset Password</CardTitle>
                    <CardDescription>
                        {step === 1 && "Enter your username to find your account"}
                        {step === 2 && "Select a recovery method"}
                        {step === 3 && (method === 'question' ? "Answer security question" : "Enter backup key")}
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {step === 1 && (
                        <Form {...usernameForm}>
                            <form onSubmit={usernameForm.handleSubmit(onCheckUser)} className="space-y-4">
                                <FormField
                                    control={usernameForm.control}
                                    name="username"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Username</FormLabel>
                                            <FormControl>
                                                <Input placeholder="Enter username" {...field} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                                <Button type="submit" className="w-full" disabled={loading}>
                                    {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Continue
                                </Button>
                            </form>
                        </Form>
                    )}

                    {step === 2 && (
                        <div className="space-y-4">
                            <Button
                                variant="outline"
                                className="w-full h-auto p-4 justify-start space-x-4"
                                disabled={!questionData}
                                onClick={() => { setMethod("question"); setStep(3); }}
                            >
                                <ShieldQuestion className="h-6 w-6" />
                                <div className="text-left">
                                    <div className="font-semibold">Security Question</div>
                                    <div className="text-xs text-muted-foreground">Answer a security question</div>
                                    {!questionData && <div className="text-xs text-red-500">Not set up</div>}
                                </div>
                            </Button>

                            <Button
                                variant="outline"
                                className="w-full h-auto p-4 justify-start space-x-4"
                                onClick={() => { setMethod("key"); setStep(3); }}
                            >
                                <KeyRound className="h-6 w-6" />
                                <div className="text-left">
                                    <div className="font-semibold">Backup Key</div>
                                    <div className="text-xs text-muted-foreground">Use your generated backup key</div>
                                </div>
                            </Button>

                            <Button variant="ghost" className="w-full" onClick={() => setStep(1)}>
                                Back
                            </Button>
                        </div>
                    )}

                    {step === 3 && (
                        <Form {...resetForm}>
                            <form onSubmit={resetForm.handleSubmit(onReset)} className="space-y-4">
                                {method === 'question' && questionData && (
                                    <div className="p-3 bg-muted rounded-md text-sm font-medium mb-4">
                                        {questionData.text}
                                    </div>
                                )}

                                <FormField
                                    control={resetForm.control}
                                    name="answer"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>
                                                {method === 'question' ? 'Answer' : 'Backup Key'}
                                            </FormLabel>
                                            <FormControl>
                                                <Input
                                                    type={method === 'question' ? 'text' : 'password'}
                                                    placeholder={method === 'question' ? 'Your answer' : 'Enter 6-digit key'}
                                                    {...field}
                                                />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />

                                <FormField
                                    control={resetForm.control}
                                    name="newPassword"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>New Password</FormLabel>
                                            <FormControl>
                                                <Input type="password" placeholder="New password" {...field} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />

                                <FormField
                                    control={resetForm.control}
                                    name="confirmPassword"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Confirm Password</FormLabel>
                                            <FormControl>
                                                <Input type="password" placeholder="Confirm password" {...field} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />

                                <div className="flex gap-2">
                                    <Button type="button" variant="outline" onClick={() => setStep(2)}>
                                        Back
                                    </Button>
                                    <Button type="submit" className="flex-1" disabled={loading}>
                                        {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                        Reset Password
                                    </Button>
                                </div>
                            </form>
                        </Form>
                    )}
                </CardContent>
                <CardFooter className="flex justify-center">
                    {step === 1 && (
                        <Link to="/login" className="flex items-center text-sm text-muted-foreground hover:text-primary">
                            <ArrowLeft className="mr-2 h-4 w-4" /> Return to Login
                        </Link>
                    )}
                </CardFooter>
            </Card>
        </div>
    );
};

export default ForgotPassword;
