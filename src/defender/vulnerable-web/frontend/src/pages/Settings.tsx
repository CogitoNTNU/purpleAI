import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import axiosInstance from "@/services/axios";
import { SessionService } from "@/services/session";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

export type User = {
  id: number;
  username: string;
  email: string;
  first_name?: string;
  last_name?: string;
  isBusinessOwner?: boolean;
  ssn?: number;
  role: string;
};

export default function Settings() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [user, setUser] = useState<User | undefined>();
  const [newPassword, setNewPassword] = useState("");
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [formData, setFormData] = useState<{
    username: string;
    first_name: string;
    last_name: string;
    ssn: number | undefined;
  }>({
    username: "",
    first_name: "",
    last_name: "",
    ssn: undefined,
  });

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const userRes = await axiosInstance.get(
          `users/${SessionService.getUserId()}/`
        );
        setUser(userRes.data);
      } catch (e) {
        console.error("Failed to fetch user:", e);
      } finally {
        setLoading(false);
      }
    };

    fetchUser();
  }, []);

  useEffect(() => {
    if (!user) return;
    setFormData({
      username: user.username || "",
      first_name: user.first_name || "",
      last_name: user.last_name || "",
      ssn: user.ssn,
    });
  }, [user, navigate]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]:
        name === "ssn" ? (value === "" ? undefined : Number(value)) : value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;

    setLoading(true);

    try {
      await axiosInstance.patch(`users/${user.id}/`, formData);
      toast.success("Profile updated successfully!");
    } catch (err: any) {
      console.error("Failed to update profile:", err);
      const errorMsg =
        err?.response?.data?.detail ||
        "Failed to update profile. Please try again.";
      toast.error(errorMsg);
    } finally {
      setLoading(false);
    }
    navigate(`/user/${user.username}`);
  };

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordLoading(true);

    try {
      await axiosInstance.post("users/update_password/", {
        new_password: newPassword,
      });
      toast.success("Password updated successfully!");
      setNewPassword("");
    } catch (err: any) {
      console.error("Password update failed:", err);
      toast.error("Failed to update password.");
    } finally {
      setPasswordLoading(false);
    }
  };

  if (!user) return null;

  return (
    <div className="container mx-auto max-w-2xl py-6">
      <Card>
        <CardHeader>
          <CardTitle>Account Settings</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-4">
              <h3 className="text-lg font-medium">Profile Information</h3>

              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  name="username"
                  value={formData.username}
                  onChange={handleChange}
                  disabled
                  className="bg-muted"
                />
                <p className="text-xs text-muted-foreground">
                  Username cannot be changed
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="first_name">First Name</Label>
                  <Input
                    id="first_name"
                    name="first_name"
                    value={formData.first_name}
                    onChange={handleChange}
                    placeholder="John"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="last_name">Last Name</Label>
                  <Input
                    id="last_name"
                    name="last_name"
                    value={formData.last_name}
                    onChange={handleChange}
                    placeholder="Doe"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="ssn">Social Security Number</Label>
                  <Input
                    id="ssn"
                    name="ssn"
                    type="number"
                    value={formData.ssn ?? ""}
                    onChange={handleChange}
                    placeholder="123456789"
                  />
                </div>
              </div>
            </div>

            <div className="space-y-4 pt-4 border-t">
              <h3 className="text-lg font-medium">Account Details</h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Email</Label>
                  <Input value={user.email} disabled className="bg-muted" />
                </div>

                <div className="space-y-2">
                  <Label>Role</Label>
                  <Input
                    value={
                      user.role === "admin"
                        ? "Administrator"
                        : user.role === "business_owner"
                        ? "Business Owner"
                        : "Reviewer"
                    }
                    disabled
                    className="bg-muted"
                  />
                </div>
              </div>
            </div>

            <div className="flex gap-3">
              <Button type="submit" disabled={loading}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {loading ? "Saving..." : "Save Changes"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate(`/user/${user.username}`)}
              >
                Cancel
              </Button>
            </div>
          </form>
          <div className="space-y-4 pt-4 border-t mt-6">
            <Label className="text-lg font-medium">Update password</Label>
            <form onSubmit={handlePasswordSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="new_password">New Password</Label>
                <Input
                  id="new_password"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Enter new password"
                />
              </div>
              <Button type="submit" disabled={passwordLoading || !newPassword}>
                Update Password
              </Button>
            </form>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
