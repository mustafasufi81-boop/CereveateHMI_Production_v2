import { useState } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Link, useNavigate } from "react-router-dom";
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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { toast } from "sonner";
import { Loader2, CheckCircle2, Copy, Shield } from "lucide-react";

const formSchema = z.object({
    username: z.string().min(3, "Username must be at least 3 characters"),
    password: z.string().min(6, "Password must be at least 6 characters"),
    confirmPassword: z.string(),
    securityQuestions: z.array(z.object({
        question: z.string().min(1, "Please select a question"),
        answer: z.string().min(1, "Answer is required")
    })).min(3, "You must answer exactly 3 security questions").max(3, "You must answer exactly 3 security questions")
}).refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
});

const Signup = () => {
    const { register } = useAuth();
    const navigate = useNavigate();
    const [loading, setLoading] = useState(false);
    const [registrationComplete, setRegistrationComplete] = useState(false);
    const [mfaToken, setMfaToken] = useState<string>("");
    const [copied, setCopied] = useState(false);

    const form = useForm<z.infer<typeof formSchema>>({
        resolver: zodResolver(formSchema),
        defaultValues: {
            username: "",
            password: "",
            confirmPassword: "",
            securityQuestions: [
                { question: "", answer: "" },
                { question: "", answer: "" },
                { question: "", answer: "" }
            ]
        },
    });

    const { fields } = useFieldArray({
        control: form.control,
        name: "securityQuestions"
    });

    async function onSubmit(values: z.infer<typeof formSchema>) {
        setLoading(true);
        try {
            const result = await register(values.username, values.password, values.securityQuestions);
            if (result.success) {
                setMfaToken(result.mfaToken || "");
                setRegistrationComplete(true);
                toast.success("Registration successful!");
            }
        } catch (error: any) {
            toast.error(error.message || "Registration failed");
        } finally {
            setLoading(false);
        }
    }

    const copyToken = () => {
        navigator.clipboard.writeText(mfaToken);
        setCopied(true);
        toast.success("Token copied to clipboard!");
        setTimeout(() => setCopied(false), 2000);
    };

    const handleContinue = () => {
        navigate("/login");
    };

    if (registrationComplete) {
        return (
            <div className="flex min-h-screen items-center justify-center bg-background p-4">
                <Card className="w-full max-w-lg">
                    <CardHeader className="space-y-1">
                        <div className="flex justify-center mb-4">
                            <CheckCircle2 className="h-16 w-16 text-green-500" />
                        </div>
                        <CardTitle className="text-2xl font-bold text-center">Registration Successful!</CardTitle>
                        <CardDescription className="text-center">
                            Save your MFA token - you'll need it to log in
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <Alert className="border-blue-200 bg-blue-50 dark:bg-blue-950 dark:border-blue-800">
                            <Shield className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                            <AlertTitle className="text-blue-900 dark:text-blue-100">Your 6-Digit MFA Token</AlertTitle>
                            <AlertDescription className="space-y-3">
                                <div className="flex items-center justify-between bg-white dark:bg-gray-900 p-4 rounded-lg border-2 border-blue-300 dark:border-blue-700 mt-3">
                                    <span className="text-3xl font-mono font-bold tracking-widest text-blue-600 dark:text-blue-400">
                                        {mfaToken}
                                    </span>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={copyToken}
                                        className="ml-4"
                                    >
                                        <Copy className="h-4 w-4 mr-2" />
                                        {copied ? "Copied!" : "Copy"}
                                    </Button>
                                </div>
                                <div className="text-sm text-blue-800 dark:text-blue-200 space-y-1">
                                    <p className="font-semibold">⚠️ Important:</p>
                                    <ul className="list-disc list-inside space-y-1 ml-2">
                                        <li>Save this token securely - you'll need it for every login</li>
                                        <li>Token is valid for 30 days</li>
                                        <li>If lost or expired, use default token: <span className="font-mono font-bold">123456</span></li>
                                        <li>Your account requires admin approval before access</li>
                                    </ul>
                                </div>
                            </AlertDescription>
                        </Alert>
                    </CardContent>
                    <CardFooter>
                        <Button onClick={handleContinue} className="w-full">
                            Continue to Login
                        </Button>
                    </CardFooter>
                </Card>
            </div>
        );
    }

    return (
        <div className="flex min-h-screen items-center justify-center bg-background p-4 py-8">
            <Card className="w-full max-w-lg">
                <CardHeader className="space-y-1">
                    <CardTitle className="text-2xl font-bold">Create an account</CardTitle>
                    <CardDescription>
                        Enter your information to create an account
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Form {...form}>
                        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                            <FormField
                                control={form.control}
                                name="username"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>Username</FormLabel>
                                        <FormControl>
                                            <Input placeholder="Choose a username" {...field} />
                                        </FormControl>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <FormField
                                    control={form.control}
                                    name="password"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Password</FormLabel>
                                            <FormControl>
                                                <Input type="password" placeholder="Create password" {...field} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
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
                            </div>

                            <div className="space-y-4 pt-4">
                                <div className="text-sm font-medium">Security Questions (Required)</div>
                                {fields.map((field, index) => (
                                    <div key={field.id} className="space-y-2 p-3 border rounded-md bg-muted/20">
                                        <FormField
                                            control={form.control}
                                            name={`securityQuestions.${index}.question`}
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className="text-xs">Question {index + 1}</FormLabel>
                                                    <FormControl>
                                                        <Input placeholder="Type your question" {...field} />
                                                    </FormControl>
                                                    <FormMessage />
                                                </FormItem>
                                            )}
                                        />
                                        <FormField
                                            control={form.control}
                                            name={`securityQuestions.${index}.answer`}
                                            render={({ field }) => (
                                                <FormItem>
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
                                ))}
                            </div>

                            <Button type="submit" className="w-full" disabled={loading}>
                                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                Sign Up
                            </Button>
                        </form>
                    </Form>
                </CardContent>
                <CardFooter className="flex justify-center text-sm text-muted-foreground">
                    Already have an account?{" "}
                    <Link to="/login" className="ml-1 text-primary hover:underline">
                        Sign in
                    </Link>
                </CardFooter>
            </Card>
        </div>
    );
};

export default Signup;
