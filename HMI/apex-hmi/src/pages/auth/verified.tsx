import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2 } from "lucide-react";
import { Link } from "react-router-dom";

const Verified = () => {
    return (
        <div className="flex min-h-screen items-center justify-center bg-background p-4">
            <Card className="w-full max-w-md text-center">
                <CardHeader>
                    <div className="flex justify-center mb-4">
                        <CheckCircle2 className="h-16 w-16 text-green-500" />
                    </div>
                    <CardTitle className="text-2xl font-bold">Registration Successful</CardTitle>
                    <CardDescription>
                        Your account has been created.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <p className="text-muted-foreground mb-4">
                        Your account will be verified by an administrator shortly. You will be able to login once approved.
                    </p>
                </CardContent>
                <CardFooter className="flex justify-center">
                    <Link to="/login">
                        <Button className="w-full">Return to Login</Button>
                    </Link>
                </CardFooter>
            </Card>
        </div>
    );
};

export default Verified;
