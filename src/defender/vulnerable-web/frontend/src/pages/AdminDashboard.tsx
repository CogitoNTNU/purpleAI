import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import axiosInstance from "@/services/axios";
import { AlertTriangle, Building2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

type Report = {
  id: number;
  review__id: number;
  review__title: string;
  review__body: string;
  review__business__id: number;
  review__business__name: string;
  review__author__id: number;
  review__author__username: string;
  reporter__username: string;
  reason: string;
  created_at: string;
};

type Claim = {
  id: number;
  business: number;
  business_name?: string;
  claimant_username?: string;
  statement: string;
  status: string;
  created_at: string;
};

export default function AdminControlPanel() {
  const [reports, setReports] = useState<Report[]>([]);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [users, setUsers] = useState<any[]>([]);

  const fetchData = async () => {
    const [reportResult, claimResult, userResult] = await Promise.allSettled([
      axiosInstance.get("reviews/review/reports/"),
      axiosInstance.get("businesses/claims/"),
      axiosInstance.get("users/"),
    ]);

    if (reportResult.status === "fulfilled")
      setReports(reportResult.value.data || []);

    if (claimResult.status === "fulfilled")
      setClaims(claimResult.value.data || []);

    if (userResult.status === "fulfilled")
      setUsers(userResult.value.data || []);
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleUpdateStatus = async (claimId: number, status: string) => {
    await axiosInstance.patch(`businesses/claims/${claimId}/`, { status });
    toast(`Claim ${status}`, {
      description:
        status === "approved"
          ? "The business has been verified and ownership transferred."
          : "The claim was rejected.",
    });
    fetchData();
  };

  const toggleUserStatus = async (userId: number) => {
    try {
      await axiosInstance.post(`users/${userId}/toggle_ban/`);
      toast.success("User status updated");
      fetchData();
    } catch {
      toast.error("Failed to update user status");
    }
  };

  const resolveReport = async (reportId: number) => {
    try {
      await axiosInstance.post(`reviews/review/${reportId}/resolve_report/`);
      toast.success("Report resolved (Review kept)");
      fetchData();
    } catch {
      toast.error("Failed to resolve report");
    }
  };

  const deleteReview = async (reviewId: number) => {
    if (!confirm("Are you sure you want to delete this review?")) return;
    try {
      await axiosInstance.delete(`reviews/review/${reviewId}/`);
      toast.success("Review deleted and report resolved");
      fetchData();
    } catch {
      toast.error("Failed to delete review");
    }
  };

  // Helper to find fresh user status from the users list
  const getUserStatus = (userId: number) => {
    const u = users.find((user) => user.id === userId);
    // If user is banned (is_banned=true), they are NOT active in this context
    return u ? !u.is_banned : true;
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Admin Control Panel</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="reports">
            <TabsList>
              <TabsTrigger value="reports">Reports</TabsTrigger>
              <TabsTrigger value="claims">Claims</TabsTrigger>
              <TabsTrigger value="users">Users</TabsTrigger>
            </TabsList>
            <TabsContent value="reports" className="space-y-4">
              {reports.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No reports found.
                </p>
              ) : (
                reports.map((r) => {
                  const isActive = getUserStatus(r.review__author__id);
                  return (
                    <div
                      key={r.id}
                      className="border rounded-lg p-4 flex flex-col gap-3"
                    >
                      <div className="flex justify-between items-start">
                        <div className="space-y-1">
                          <h4 className="font-semibold flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4 text-yellow-600" />
                            Report #{r.id} - Reason:{" "}
                            <span className="text-destructive">{r.reason}</span>
                          </h4>
                          <div className="text-sm text-muted-foreground">
                            Reported by:{" "}
                            <span className="font-medium text-foreground">
                              {r.reporter__username}
                            </span>
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => resolveReport(r.id)}
                          >
                            Keep (Resolve)
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => deleteReview(r.review__id)}
                          >
                            Delete Review
                          </Button>
                        </div>
                      </div>

                      <div className="bg-muted/50 p-3 rounded-md space-y-2">
                        <div className="flex justify-between items-center text-sm">
                          <span className="font-medium text-primary">
                            Business: {r.review__business__name}
                          </span>
                          <span className="text-muted-foreground text-xs">
                            RID: {r.review__id}
                          </span>
                        </div>
                        <div className="space-y-1">
                          <p className="font-medium">
                            {r.review__title || "Untitled Review"}
                          </p>
                          <p className="text-sm text-muted-foreground">
                            {r.review__body}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center justify-between text-sm pt-2 border-t">
                        <div className="flex items-center gap-2">
                          <span>
                            Author:{" "}
                            <span className="font-medium">
                              {r.review__author__username}
                            </span>
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] ${
                              isActive
                                ? "bg-green-100 text-green-800"
                                : "bg-red-100 text-red-800"
                            }`}
                          >
                            {isActive ? "Active" : "Banned"}
                          </span>
                        </div>
                        <Button
                          size="sm"
                          variant={isActive ? "destructive" : "outline"}
                          className="h-7 text-xs"
                          onClick={() => toggleUserStatus(r.review__author__id)}
                        >
                          {isActive ? "Ban User" : "Unban User"}
                        </Button>
                      </div>
                    </div>
                  );
                })
              )}
            </TabsContent>
            <TabsContent value="claims">
              {claims.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No claims found.
                </p>
              ) : (
                claims.map((claim) => (
                  <div
                    key={claim.id}
                    className="p-3 border rounded-md flex flex-col sm:flex-row justify-between mb-2"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <Building2 className="h-4 w-4 text-blue-600" />
                        <p className="font-medium">{claim.business_name}</p>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        By {claim.claimant_username || "N/A"} – {claim.status}
                      </p>
                      <p className="text-sm">{claim.statement}</p>
                    </div>

                    {claim.status === "pending" && (
                      <div className="flex gap-2 mt-2 sm:mt-0">
                        <Button
                          size="sm"
                          onClick={() =>
                            handleUpdateStatus(claim.id, "approved")
                          }
                        >
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() =>
                            handleUpdateStatus(claim.id, "rejected")
                          }
                        >
                          Reject
                        </Button>
                      </div>
                    )}
                  </div>
                ))
              )}
            </TabsContent>
            <TabsContent value="users">
              <Card>
                <CardHeader>
                  <CardTitle>User Management</CardTitle>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Username</TableHead>
                        <TableHead>Email</TableHead>
                        <TableHead>Role</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {users.map((u) => (
                        <TableRow key={u.id}>
                          <TableCell>{u.username}</TableCell>
                          <TableCell>{u.email}</TableCell>
                          <TableCell className="capitalize">{u.role}</TableCell>
                          <TableCell>
                            <span
                              className={`px-2 py-1 rounded-full text-xs ${
                                !u.is_banned
                                  ? "bg-green-100 text-green-800"
                                  : "bg-red-100 text-red-800"
                              }`}
                            >
                              {!u.is_banned ? "Active" : "Banned"}
                            </span>
                          </TableCell>
                          <TableCell>
                            {u.role !== "admin" && (
                              <Button
                                variant={
                                  !u.is_banned ? "destructive" : "outline"
                                }
                                size="sm"
                                onClick={() => toggleUserStatus(u.id)}
                              >
                                {!u.is_banned ? "Ban" : "Unban"}
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
