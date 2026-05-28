import { useState, useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useNavigate } from "react-router-dom";
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
import { Loader2, ShieldQuestion, KeyRound, Lock } from "lucide-react";
import api from "@/services/api";

const formSchema = z.object({
    code: z.string().optional(),
    answer: z.string().optional(),
});

const MfaVerify = () => {
    const { tempToken, verifyMfa, cancelMfa } = useAuth();
    const navigate = useNavigate();
    const [method, setMethod] = useState<"code" | "question">("code");
    const [questionData, setQuestionData] = useState<{ index: number; text: string } | null>(null);
    const [loading, setLoading] = useState(false);
    const [fetchingQuestion, setFetchingQuestion] = useState(false);

    useEffect(() => {
        if (!tempToken) {
            navigate("/login");
        }
    }, [tempToken, navigate]);

    const form = useForm<z.infer<typeof formSchema>>({
        resolver: zodResolver(formSchema),
        defaultValues: {
            code: "",
            answer: "",
        },
    });

    const fetchQuestion = async () => {
        if (!tempToken) return;
        if (questionData) {
            setMethod("question");
            return;
        }
        setFetchingQuestion(true);
        try {
            // We need to pass the tempToken to get the question
            const response = await api.post('/auth/mfa/question', { tempToken });
            if (response.data && response.data.available) {
                setQuestionData({
                    index: response.data.index,
                    text: response.data.question
                });
                setMethod("question");
            } else {
                toast.error("No security questions available");
            }
        } catch (error: any) {
            toast.error("Failed to load security question");
        } finally {
            setFetchingQuestion(false);
        }
    };

    const onSubmit = async (values: z.infer<typeof formSchema>) => {
        setLoading(true);
        try {
            if (method === "code" && values.code) {
                const result = await verifyMfa(values.code);
                if (result.success) navigate("/");
            } else if (method === "question" && values.answer && questionData) {
                const result = await verifyMfa(undefined, questionData.index, values.answer);
                if (result.success) navigate("/");
            } else {
                toast.error("Please enter a code or answer");
            }
        } catch (error: any) {
            toast.error(error.message || "Verification failed");
        } finally {
            setLoading(false);
        }
    };

    const handleCancel = () => {
        cancelMfa();
        navigate("/login");
    };

    return (
        <div className="flex min-h-screen items-center justify-center bg-background p-4">
            <Card className="w-full max-w-md">
                <CardHeader>
                    <div className="flex justify-center mb-4">
                        <Lock className="h-12 w-12 text-blue-500" />
                    </div>
                    <CardTitle className="text-2xl font-bold text-center">Multi-Factor Authentication</CardTitle>
                    <CardDescription className="text-center">
                        {method === "code" 
                            ? "Enter your 6-digit MFA token (received during registration)" 
                            : "Answer your security question"}
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex justify-center space-x-2 mb-6">
                        <Button
                            variant={method === "code" ? "default" : "outline"}
                            size="sm"
                            onClick={() => setMethod("code")}
                        >
                            <KeyRound className="mr-2 h-4 w-4" />
                            MFA Token
                        </Button>
                        <Button
                            variant={method === "question" ? "default" : "outline"}
                            size="sm"
                            onClick={() => { setMethod("question"); fetchQuestion(); }}
                            disabled={fetchingQuestion}
                        >
                            {fetchingQuestion ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ShieldQuestion className="mr-2 h-4 w-4" />}
                            Security Question
                        </Button>
                    </div>

                    <Form {...form}>
                        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                            {method === "code" && (
                                <>
                                    <FormField
                                        control={form.control}
                                        name="code"
                                        render={({ field }) => (
                                            <FormItem>
                                                <FormLabel>6-Digit MFA Token</FormLabel>
                                                <FormControl>
                                                    <Input 
                                                        placeholder="Enter 6-digit token" 
                                                        type="password"
                                                        autoComplete="one-time-code"
                                                        {...field} 
                                                        maxLength={6}
                                                        className="text-center text-2xl tracking-widest font-mono"
                                                    />
                                                </FormControl>
                                                <FormMessage />
                                                <p className="text-xs text-muted-foreground mt-2">
                                                    Use the 6-digit backup key you received during registration.
                                                    If your key has expired, contact an administrator to regenerate it.
                                                </p>
                                            </FormItem>
                                        )}
                                    />
                                </>
                            )}

                            {method === "question" && questionData && (
                                <div className="space-y-4">
                                    <div className="p-3 bg-muted rounded-md text-sm font-medium">
                                        {questionData.text}
                                    </div>
                                    <FormField
                                        control={form.control}
                                        name="answer"
                                        render={({ field }) => (
                                            <FormItem>
                                                <FormLabel>Answer</FormLabel>
                                                <FormControl>
                                                    <Input
                                                        {...field}
                                                        type="password"
                                                        placeholder="Your answer"
                                                        autoComplete="new-password"
                                                        name="sq_ans_nofill"
                                                        id="sq_ans_nofill"
                                                        data-lpignore="true"
                                                        data-form-type="other"
                                                    />
                                                </FormControl>
                                                <FormMessage />
                                            </FormItem>
                                        )}
                                    />
                                </div>
                            )}

                            <div className="flex gap-2 pt-2">
                                <Button type="button" variant="ghost" onClick={handleCancel} className="flex-1">
                                    Cancel
                                </Button>
                                <Button type="submit" className="flex-1" disabled={loading}>
                                    {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Verify
                                </Button>
                            </div>
                        </form>
                    </Form>
                </CardContent>
            </Card>
        </div>
    );
};

export default MfaVerify;
