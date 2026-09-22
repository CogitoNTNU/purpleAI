import { useEffect, useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { useAuth } from "@/services/AuthContext";
import axiosInstance from "@/services/axios";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

type Business = {
  id: number;
  name: string;
  category: string;
  verified: boolean;
};

export default function Dashboard() {
  const { user } = useAuth();
  const [businesses, setBusinesses] = useState<Business[]>([]);

  useEffect(() => {
    if (user) {
      axiosInstance
        .get("businesses/?q=&")
        .then((res) => {
          const mine = (res.data.results || res.data).filter(
            (b: any) => b.creator_username === user.username
          );
          setBusinesses(mine);
        })
        .catch(() => {});
    }
  }, [user]);

  if (!user) return <p className="text-sm text-destructive">Please log in.</p>;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>My Profile</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div>
            <span className="font-medium">Username: </span>
            {user.username}
          </div>
          <div>
            <span className="font-medium">Email: </span>
            {user.email}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>My Businesses</CardTitle>
        </CardHeader>
        <CardContent>
          {businesses.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              You haven’t created any businesses yet.
            </p>
          ) : (
            <ul className="space-y-2">
              {businesses.map((b) => (
                <li key={b.id} className="flex justify-between items-center">
                  <Link
                    to={`/business/${b.id}`}
                    className="text-primary hover:underline"
                  >
                    {b.name} ({b.category})
                  </Link>
                  {b.verified && (
                    <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">
                      Verified
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4">
            <Link to="/business/new">
              <Button size="sm">Add New Business</Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
