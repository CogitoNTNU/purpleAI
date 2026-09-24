import WriteReview from "@/components/WriteReview";
import ReviewItem from "@/components/ReviewItem";
import ClaimBusiness from "@/components/ClaimBusiness";
import EditBusinessDialog from "@/components/EditBusinessDialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import axiosInstance from "@/services/axios";
import { Calendar, MapPin, Star } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "@/services/AuthContext";
import type { Business } from "./Businesses";

export default function BusinessDetail() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [business, setBusiness] = useState<Business | null>(null);
  const [reviews, setReviews] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    if (!id) return;
    try {
      const [bRes, rRes] = await Promise.all([
        axiosInstance.get(`businesses/${id}/`),
        axiosInstance.get(`reviews/review/?business=${id}`),
      ]);
      setBusiness(bRes.data);
      setReviews(rRes.data);
    } catch (e) {
      console.error("Error fetching business:", e);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const renderStars = (rating: number) => (
    <div className="flex">
      {[1, 2, 3, 4, 5].map((v) => (
        <Star
          key={v}
          className={`h-4 w-4 ${
            v <= rating ? "text-yellow-400 fill-yellow-400" : "text-gray-300"
          }`}
        />
      ))}
    </div>
  );

  if (loading)
    return (
      <div className="min-h-[50vh] flex items-center justify-center text-muted-foreground">
        Loading...
      </div>
    );

  if (!business)
    return (
      <div className="text-center text-sm mt-16 text-muted-foreground">
        Business not found.
      </div>
    );

  const avg =
    typeof business.average_rating === "string"
      ? parseFloat(business.average_rating)
      : business.average_rating;

  return (
    <div className="container mx-auto max-w-5xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex justify-between items-center flex-wrap gap-2">
            <span className="text-2xl font-bold">{business.name}</span>
            <div className="flex items-center gap-2">
              {business.verified && (
                <span className="text-xs px-2 py-1 rounded-full bg-blue-100 text-blue-800">
                  Verified
                </span>
              )}
              {user?.id === business.owner && !business.verified && (
                <ClaimBusiness businessId={business.id} />
              )}
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-muted-foreground">
          {business.description && <p>{business.description}</p>}

          <div className="flex flex-wrap gap-3 text-sm items-center">
            <span className="capitalize">{business.category}</span>
            <span className="flex items-center gap-1">
              <MapPin className="h-4 w-4" />
              {business.address || "Address not provided"}
            </span>
            <span className="flex items-center gap-1">
              <Calendar className="h-4 w-4" />
              Since {new Date(business.created_at).getFullYear()}
            </span>
            <span className="flex items-center gap-1">
              {renderStars(Math.round(avg ?? 0))}
              <span>{avg?.toFixed(1) ?? "0.0"}</span>
            </span>
            <WriteReview
              className="ml-auto"
              businessId={business.id}
              onReviewPosted={fetchData}
            />
          </div>
          {user?.id === business.owner && (
             <div className="flex justify-end pt-4 border-t mt-4">
                <EditBusinessDialog business={business} onUpdate={fetchData} />
             </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Reviews ({reviews.length})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {reviews.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No reviews yet. Be the first to write one!
            </p>
          ) : (
            reviews.map((r) => (
              <ReviewItem
                key={r.id}
                review={r}
                businessOwnerId={business.owner ?? undefined}
                onAction={fetchData}
              />
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
