import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/auth-context";
import { authService } from "@/services/auth-service";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { toast } from "sonner";
import { Loader2, CheckCircle2, Copy, Shield, KeyRound } from "lucide-react";

// ─── Step indicators ─────────────────────────────────────────────────────────
const STEPS = ["New Password", "Security Questions", "Your MFA Token"];

// ─── Component ────────────────────────────────────────────────────────────────
const ForcePasswordSetup = () => {
    const { setupToken } = useAuth();
    const navigate = useNavigate();

    const [step, setStep] = useState(1);
    const [loading, setLoading] = useState(false);
    const [copied, setCopied] = useState(false);
    const [mfaToken, setMfaToken] = useState("");

    // Step 1
    const [newPassword, setNewPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [pwError, setPwError] = useState("");

    // Step 2 – three security questions
    const [questions, setQuestions] = useState([
        { question: "", answer: "" },
        { question: "", answer: "" },
        { question: "", answer: "" },
    ]);
    const [sqError, setSqError] = useState("");

    // ── Helpers ───────────────────────────────────────────────────────────────
    const updateQuestion = (index: number, field: "question" | "answer", value: string) => {
        const updated = [...questions];
        updated[index] = { ...updated[index], [field]: value };
        setQuestions(updated);
    };

    // ── Step 1 → Step 2 ───────────────────────────────────────────────────────
    const handlePasswordNext = () => {
        setPwError("");
        if (newPassword.length < 6) {
            setPwError("Password must be at least 6 characters.");
            return;
        }
        if (newPassword !== confirmPassword) {
            setPwError("Passwords do not match.");
            return;
        }
        setStep(2);
    };

    // ── Step 2 → Submit → Step 3 ──────────────────────────────────────────────
    const handleSubmit = async () => {
        setSqError("");
        for (let i = 0; i < questions.length; i++) {
            if (!questions[i].question.trim()) {
                setSqError(`Question ${i + 1} cannot be empty.`);
                return;
            }
            if (!questions[i].answer.trim()) {
                setSqError(`Answer ${i + 1} cannot be empty.`);
                return;
            }
        }
        if (!setupToken) {
            toast.error("Setup session expired. Please log in again.");
            navigate("/login");
            return;
        }
        setLoading(true);
        try {
            const result = await authService.completeSetup(setupToken, newPassword, questions);
            setMfaToken(result.mfaToken || "");
            setStep(3);
            toast.success("Password setup complete!");
        } catch (error: any) {
            toast.error(error.response?.data?.message || "Setup failed. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    const copyToken = () => {
        navigator.clipboard.writeText(mfaToken);
        setCopied(true);
        toast.success("Token copied to clipboard!");
        setTimeout(() => setCopied(false), 2000);
    };

    // ── Render ─────────────────────────────────────────────────────────────────
    return (
        <div className="flex min-h-screen items-center justify-center bg-background p-4">
            <Card className="w-full max-w-lg">
                {/* Header */}
                <CardHeader className="space-y-1">
                    <div className="flex justify-center mb-2">
                        <KeyRound className="h-12 w-12 text-primary" />
                    </div>
                    <CardTitle className="text-2xl font-bold text-center">Account Setup Required</CardTitle>
                    <CardDescription className="text-center">
                        Your password was reset by an administrator. Complete the steps below to regain access.
                    </CardDescription>
                    {/* Step pills */}
                    <div className="flex justify-center gap-2 pt-2">
                        {STEPS.map((label, i) => (
                            <div key={i} className="flex flex-col items-center gap-1">
                                <div
                                    className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-colors ${
                                        step > i + 1
                                            ? "bg-green-500 border-green-500 text-white"
                                            : step === i + 1
                                            ? "bg-primary border-primary text-primary-foreground"
                                            : "bg-muted border-muted-foreground/30 text-muted-foreground"
                                    }`}
                                >
                                    {step > i + 1 ? "✓" : i + 1}
                                </div>
                                <span className="text-xs text-muted-foreground">{label}</span>
                            </div>
                        ))}
                    </div>
                </CardHeader>

                <CardContent className="space-y-4">
                    {/* ── STEP 1: New Password ── */}
                    {step === 1 && (
                        <div className="space-y-4">
                            <div className="space-y-2">
                                <label className="text-sm font-medium">New Password</label>
                                <Input
                                    type="password"
                                    placeholder="Minimum 6 characters"
                                    value={newPassword}
                                    onChange={e => setNewPassword(e.target.value)}
                                />
                            </div>
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Confirm Password</label>
                                <Input
                                    type="password"
                                    placeholder="Re-enter your new password"
                                    value={confirmPassword}
                                    onChange={e => setConfirmPassword(e.target.value)}
                                    onKeyDown={e => e.key === "Enter" && handlePasswordNext()}
                                />
                            </div>
                            {pwError && <p className="text-sm text-destructive">{pwError}</p>}
                            <Button className="w-full" onClick={handlePasswordNext}>
                                Next: Security Questions
                            </Button>
                        </div>
                    )}

                    {/* ── STEP 2: Security Questions ── */}
                    {step === 2 && (
                        <div className="space-y-4">
                            <p className="text-sm text-muted-foreground">
                                Set 3 security questions. These will be used to verify your identity if you forget your password.
                            </p>
                            {questions.map((q, index) => (
                                <div key={index} className="space-y-2 p-3 border rounded-md bg-muted/20">
                                    <label className="text-xs font-medium">Question {index + 1}</label>
                                    <Input
                                        placeholder={`Type security question ${index + 1}`}
                                        value={q.question}
                                        onChange={e => updateQuestion(index, "question", e.target.value)}
                                    />
                                    <Input
                                        placeholder="Your answer"
                                        value={q.answer}
                                        onChange={e => updateQuestion(index, "answer", e.target.value)}
                                    />
                                </div>
                            ))}
                            {sqError && <p className="text-sm text-destructive">{sqError}</p>}
                            <div className="flex gap-2">
                                <Button variant="outline" className="flex-1" onClick={() => setStep(1)}>
                                    Back
                                </Button>
                                <Button className="flex-1" onClick={handleSubmit} disabled={loading}>
                                    {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Complete Setup
                                </Button>
                            </div>
                        </div>
                    )}

                    {/* ── STEP 3: MFA Token ── */}
                    {step === 3 && (
                        <div className="space-y-4">
                            <div className="flex justify-center">
                                <CheckCircle2 className="h-16 w-16 text-green-500" />
                            </div>
                            <Alert className="border-blue-200 bg-blue-50 dark:bg-blue-950 dark:border-blue-800">
                                <Shield className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                                <AlertTitle className="text-blue-900 dark:text-blue-100">Your New 6-Digit MFA Token</AlertTitle>
                                <AlertDescription className="space-y-3">
                                    <div className="flex items-center justify-between bg-white dark:bg-gray-900 p-4 rounded-lg border-2 border-blue-300 dark:border-blue-700 mt-3">
                                        <span className="text-3xl font-mono font-bold tracking-widest text-blue-600 dark:text-blue-400">
                                            {mfaToken}
                                        </span>
                                        <Button variant="outline" size="sm" onClick={copyToken} className="ml-4">
                                            <Copy className="h-4 w-4 mr-2" />
                                            {copied ? "Copied!" : "Copy"}
                                        </Button>
                                    </div>
                                    <div className="text-sm text-blue-800 dark:text-blue-200 space-y-1">
                                        <p className="font-semibold">⚠️ Important:</p>
                                        <ul className="list-disc list-inside space-y-1 ml-2">
                                            <li>Save this token — you'll need it for every login</li>
                                            <li>Token is valid for 30 days</li>
                                            <li>If lost or expired, contact your administrator</li>
                                        </ul>
                                    </div>
                                </AlertDescription>
                            </Alert>
                        </div>
                    )}
                </CardContent>

                {step === 3 && (
                    <CardFooter>
                        <Button className="w-full" onClick={() => navigate("/login")}>
                            Continue to Login
                        </Button>
                    </CardFooter>
                )}
            </Card>
        </div>
    );
};

export default ForcePasswordSetup;
