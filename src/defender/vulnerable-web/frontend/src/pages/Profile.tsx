import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import axiosInstance from "@/services/axios";
import { useAuth } from "@/services/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Star, MessageSquare, Edit, Building2 } from "lucide-react";

type UserProfile = {
  id: number;
  username: string;
  full_name: string;
  email: string;
  role: string;
  is_banned: false;
};

type UserReview = {
  id: number;
  business: number;
  business_name: string;
  rating: number;
  title: string;
  body: string;
  created_at: string;
  helpful_count: number;
};

type Business = {
  id: number;
  name: string;
  category: string;
  verified: boolean;
};

export default function UserProfile() {
  const { username } = useParams<{ username: string }>();
  const { user: currentUser } = useAuth();
  const navigate = useNavigate();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [reviews, setReviews] = useState<UserReview[]>([]);
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [loading, setLoading] = useState(true);

  const isOwnProfile = currentUser?.username === username;

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        // Fetch user data
        const userRes = await axiosInstance.get(`users/username/${username}/`);
        const userData = Array.isArray(userRes.data)
          ? userRes.data[0]
          : userRes.data;
        setUser(userData);

        // Fetch user's reviews using ID
        const reviewsRes = await axiosInstance.get(
          `reviews/review/?author=${userData.id}`
        );
        const userReviews = reviewsRes.data;

        // Enhance with business names
        const enhancedReviews = await Promise.all(
          userReviews.map(async (review: any) => {
            try {
              const bizRes = await axiosInstance.get(
                `businesses/${review.business}/`
              );
              return { ...review, business_name: bizRes.data.name };
            } catch {
              return { ...review, business_name: "Unknown Business" };
            }
          })
        );
        setReviews(enhancedReviews);

        // If own profile, fetch owned businesses
        if (isOwnProfile && currentUser) {
          const bizRes = await axiosInstance.get("businesses/");
          const allBiz = bizRes.data.results || bizRes.data;
          const ownedBiz = allBiz.filter((b: any) => b.owner === userData.id);
          setBusinesses(ownedBiz);
        }
      } catch (e) {
        console.error("Failed to fetch profile:", e);
      } finally {
        setLoading(false);
      }
    };

    if (username) fetchProfile();
  }, [username, currentUser, isOwnProfile]);

  if (loading)
    return (
      <div className="flex justify-center items-center min-h-64">
        Loading...
      </div>
    );

  if (!user)
    return (
      <div className="text-center mt-16 text-muted-foreground">
        User not found
      </div>
    );

  const totalHelpful = reviews.reduce(
    (sum, r) => sum + (r.helpful_count || 0),
    0
  );
  const avgRating =
    reviews.length > 0
      ? (
          reviews.reduce((sum, r) => sum + r.rating, 0) / reviews.length
        ).toFixed(1)
      : "0.0";

  return (
    <div className="container mx-auto max-w-4xl space-y-6">
      <Card>
        <CardHeader>
          <div className="flex justify-between items-start">
            <CardTitle className="text-2xl flex gap-2 items-center">
              {user.full_name}
              <p className="text-xl text-muted-foreground">({user.username})</p>
            </CardTitle>

            {isOwnProfile && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate("/settings")}
              >
                <Edit className="h-4 w-4 mr-2" />
                Edit Profile
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="text-center p-4 bg-muted rounded-lg">
              <MessageSquare className="h-6 w-6 mx-auto mb-2 text-primary" />
              <div className="text-2xl font-bold">{reviews.length}</div>
              <div className="text-sm text-muted-foreground">Reviews</div>
            </div>
            <div className="text-center p-4 bg-muted rounded-lg">
              <Star className="h-6 w-6 mx-auto mb-2 text-yellow-400 fill-yellow-400" />
              <div className="text-2xl font-bold">{avgRating}</div>
              <div className="text-sm text-muted-foreground">Avg Rating</div>
            </div>
            <div className="text-center p-4 bg-muted rounded-lg">
              <div className="text-2xl font-bold">{totalHelpful}</div>
              <div className="text-sm text-muted-foreground">Helpful Votes</div>
            </div>
          </div>

          {isOwnProfile && user.email && (
            <div className="mt-4">
              <span className="font-medium">Email: </span>
              <span className="text-muted-foreground">{user.email}</span>
            </div>
          )}

          <div className="mt-2">
            <span
              className={`inline-block px-3 py-1 rounded-full text-xs ${
                user.role === "admin"
                  ? "bg-red-100 text-red-800"
                  : user.role === "business_owner"
                  ? "bg-blue-100 text-blue-800"
                  : "bg-gray-100 text-gray-800"
              }`}
            >
              {user.role === "admin"
                ? "Administrator"
                : user.role === "business_owner"
                ? "Business Owner"
                : "Reviewer"}
            </span>
          </div>
        </CardContent>
      </Card>

      {isOwnProfile && (
        <Card>
          <CardHeader>
            <div className="flex justify-between items-center">
              <CardTitle className="flex items-center gap-2">
                <Building2 className="h-5 w-5" />
                My Businesses
              </CardTitle>
              <Link to="/business/new">
                <Button size="sm">Add Business</Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            {businesses.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                You haven't created any businesses yet.
              </p>
            ) : (
              <ul className="space-y-2">
                {businesses.map((b) => (
                  <li
                    key={b.id}
                    className="flex justify-between items-center py-2 border-b last:border-none"
                  >
                    <Link
                      to={`/business/${b.id}`}
                      className="text-primary hover:underline"
                    >
                      {b.name}{" "}
                      <span className="text-xs text-muted-foreground">
                        ({b.category})
                      </span>
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
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Reviews ({reviews.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {reviews.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              No reviews yet
            </p>
          ) : (
            <div className="space-y-4">
              {reviews.map((review) => (
                <div key={review.id} className="border-b pb-4 last:border-none">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex-1">
                      <Link
                        to={`/business/${review.business}`}
                        className="text-primary hover:underline font-medium"
                      >
                        {review.business_name}
                      </Link>
                      <div className="flex items-center gap-2 mt-1">
                        <div className="flex">
                          {[1, 2, 3, 4, 5].map((s) => (
                            <Star
                              key={s}
                              className={`h-4 w-4 ${
                                s <= review.rating
                                  ? "text-yellow-400 fill-yellow-400"
                                  : "text-gray-300"
                              }`}
                            />
                          ))}
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {new Date(review.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  </div>
                  {review.title && (
                    <h4 className="font-medium mb-1">{review.title}</h4>
                  )}
                  <p className="text-sm text-muted-foreground mb-2">
                    {review.body}
                  </p>
                  {review.helpful_count > 0 && (
                    <span className="text-xs text-muted-foreground">
                      {review.helpful_count} found this helpful
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
